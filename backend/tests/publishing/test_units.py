from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import session_scope
from app.db.models import OAuthState, PlatformAccount, PublishJob
from app.publishing.base import PublishErrorType, PublishStatus
from app.publishing.capabilities import PublishingStatus, load_capabilities
from app.publishing.crypto import decrypt_token, encrypt_token, mask_token
from app.publishing.idempotency import make_idempotency_key, media_hash
from app.publishing.oauth import complete_authorization, start_authorization
from app.publishing.polling import PollingManager
from app.publishing.publishers import all_publisher_platforms, get_publisher
from app.publishing import retry as retry_mod
from app.publishing.scheduler import due_jobs, schedule_job, to_utc
from app.publishing.token_manager import connection_state, ensure_valid
from app.publishing.webhooks import apply_webhook, sign, verify_signature
from app.publishing.base import PublishError


# ---- capability registry ------------------------------------------- #

def test_capabilities_cover_all_platforms():
    caps = load_capabilities()
    assert set(caps) == set(all_publisher_platforms())
    assert caps["naver_clip"].publishing_status == PublishingStatus.NOT_SUPPORTED.value
    assert caps["naver_blog"].publishing_status == PublishingStatus.MANUAL_ONLY.value
    assert caps["tiktok"].app_review_required is True
    assert caps["youtube"].video_supported and not caps["youtube"].carousel_supported
    for c in caps.values():
        assert c.last_verified_at


# ---- credential security ------------------------------------------- #

def test_token_encryption_roundtrip_and_masking():
    enc = encrypt_token("ya29.super-secret-token-value")
    assert enc != "ya29.super-secret-token-value"
    assert decrypt_token(enc) == "ya29.super-secret-token-value"
    assert mask_token("ya29.super-secret-token-value").startswith("ya29")
    assert mask_token("ya29.super-secret-token-value").endswith("alue")
    assert "secret" not in mask_token("ya29.super-secret-token-value")


# ---- oauth state / CSRF ------------------------------------------ #

def test_oauth_state_is_validated_and_single_use():
    with session_scope() as s:
        info = start_authorization(s, "youtube")
        state = info["state"]
        assert "code_challenge" in info["authorization_url"]
    with session_scope() as s:
        bundle = complete_authorization(s, "youtube", state, "auth-code-123")
        assert bundle["access_token"].startswith("mock-access-")
    with session_scope() as s, pytest.raises(PublishError):
        complete_authorization(s, "youtube", state, "auth-code-123")  # replay rejected
    with session_scope() as s, pytest.raises(PublishError):
        complete_authorization(s, "youtube", "not-a-real-state", "x")  # forged state


# ---- token manager --------------------------------------------- #

def test_connection_state_transitions():
    a = PlatformAccount(platform="youtube", scopes=["https://www.googleapis.com/auth/youtube.upload",
                                                    "https://www.googleapis.com/auth/youtube.readonly"],
                        access_token_encrypted=encrypt_token("t"),
                        refresh_token_encrypted=encrypt_token("r"))
    a.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
    assert connection_state(a) == "CONNECTED"
    a.token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=3)
    assert connection_state(a) == "TOKEN_EXPIRING"
    a.token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert connection_state(a) == "REFRESH_REQUIRED"
    a.refresh_token_encrypted = None
    assert connection_state(a) == "REAUTH_REQUIRED"


def test_ensure_valid_refreshes_once_then_no_infinite_loop(connect_account):
    aid = connect_account("youtube")
    with session_scope() as s:
        acct = s.get(PlatformAccount, aid)
        acct.token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        acct.refresh_token_encrypted = encrypt_token("revoked-token")
        with pytest.raises(PublishError) as ei:
            ensure_valid(s, acct)
        assert ei.value.error_type == PublishErrorType.AUTH_REVOKED
        assert acct.connection_status == "REAUTH_REQUIRED"


# ---- idempotency ------------------------------------------- #

def test_idempotency_key_is_stable_and_input_sensitive():
    k1 = make_idempotency_key(platform="x", account_id="a", content_id="c",
                              scheduled_at="asap", media_hash_=media_hash(["h1", "h2"]))
    k2 = make_idempotency_key(platform="x", account_id="a", content_id="c",
                              scheduled_at="asap", media_hash_=media_hash(["h2", "h1"]))
    k3 = make_idempotency_key(platform="x", account_id="a", content_id="c2",
                              scheduled_at="asap", media_hash_=media_hash(["h1", "h2"]))
    assert k1 == k2 and k1 != k3 and len(k1) == 40


# ---- retry engine --------------------------------------- #

def test_retry_plan_backoff_terminal_and_deadletter():
    p1 = retry_mod.plan(PublishErrorType.NETWORK_TIMEOUT, attempt=1, max_attempts=5)
    p2 = retry_mod.plan(PublishErrorType.NETWORK_TIMEOUT, attempt=2, max_attempts=5)
    assert p1["retry"] and p2["retry"]
    assert p2["delay_seconds"] > p1["delay_seconds"]          # exponential
    assert retry_mod.plan(PublishErrorType.POLICY_REJECTION, attempt=1, max_attempts=5)["retry"] is False
    assert retry_mod.plan(PublishErrorType.AUTH_REVOKED, attempt=1, max_attempts=5)["action"] == "REAUTH_REQUIRED"
    assert retry_mod.plan(PublishErrorType.DUPLICATE, attempt=1, max_attempts=5)["dead_letter"] is True
    assert retry_mod.plan(PublishErrorType.UNKNOWN, attempt=5, max_attempts=5)["dead_letter"] is True


# ---- polling (bounded) --------------------------------- #

def test_polling_manager_is_bounded():
    pm = PollingManager(schedule=[1, 1, 1], max_seconds=3)
    calls = {"n": 0}

    def step():
        calls["n"] += 1
        return calls["n"]

    done, last = pm.run(step=step, done=lambda r: False, sleep=lambda _s: None)
    assert done is False
    assert calls["n"] <= 6            # does not spin forever


# ---- webhook signature --------------------------------- #

def test_webhook_signature_gate(_base_settings):
    _base_settings.webhook_secret = "top-secret"
    body = b'{"remote_post_id":"p1","status":"PUBLISHED"}'
    good = sign(body, secret="top-secret")
    assert verify_signature(body, good, secret="top-secret") is True
    assert verify_signature(body, "sha256=deadbeef", secret="top-secret") is False
    assert verify_signature(body, None, secret="top-secret") is False


def test_forged_webhook_cannot_publish():
    with session_scope() as s:
        res = apply_webhook(s, "instagram", {"remote_post_id": "p1", "status": "PUBLISHED"},
                            verified=False)
    assert res["accepted"] is False


# ---- scheduler --------------------------------------- #

def test_scheduler_utc_and_due_query(connect_account):
    aid = connect_account("youtube")
    kst = to_utc(datetime(2026, 8, 31, 9, 0), "Asia/Seoul")
    assert kst.tzinfo == timezone.utc and kst.hour == 0        # 09:00 KST == 00:00 UTC

    import uuid
    from app.db.models import Campaign

    cid = str(uuid.uuid4())
    with session_scope() as s:
        s.add(Campaign(id=cid, topic="t", platforms=["youtube"], status="SUCCESS"))
        job = PublishJob(campaign_id=cid, platform="youtube", platform_account_id=aid,
                         content_type="SHORT_VIDEO", idempotency_key="k-sched",
                         max_attempts=5)
        s.add(job)
        s.flush()
        schedule_job(s, job, datetime.now() - timedelta(minutes=5), "Asia/Seoul")
    with session_scope() as s:                                  # fresh session == "after restart"
        due = due_jobs(s)
        assert any(j.idempotency_key == "k-sched" for j in due)


# ---- publishers: capability + a mock publish ----------- #

@pytest.mark.parametrize("platform", ["youtube", "instagram", "facebook", "threads",
                                      "x", "pinterest", "linkedin"])
def test_publisher_capability_and_dry_run(platform):
    pub = get_publisher(platform, {"connection_status": "CONNECTED", "account_type": "BUSINESS"})
    cap = pub.get_capabilities()
    assert cap.integration_status == "MOCK_TESTED"
    from app.publishing.base import PublishRequest

    req = PublishRequest(job_id="j", platform=platform, account_id="a",
                         content_type="SHORT_VIDEO", caption="hi",
                         platform_settings={"board_id": "b1"}, dry_run=True)
    res = pub.publish(req)
    assert res.status == PublishStatus.READY
    assert res.detail.get("dry_run") is True


def test_naver_publishers_are_honest():
    blog = get_publisher("naver_blog", {"connection_status": "CONNECTED"})
    from app.publishing.base import PublishRequest

    r = blog.publish(PublishRequest(job_id="j", platform="naver_blog", account_id="a",
                                    content_type="BLOG_ARTICLE", title="t", description="body"))
    assert r.status == PublishStatus.WAITING_USER_ACTION
    assert r.detail["type"] == "NAVER_BLOG_PACKAGE"
    assert r.detail["browser_assist_enabled"] is False

    clip = get_publisher("naver_clip", {"connection_status": "CONNECTED"})
    rc = clip.publish(PublishRequest(job_id="j", platform="naver_clip", account_id="a",
                                     content_type="SHORT_VIDEO"))
    assert rc.status == PublishStatus.NOT_SUPPORTED
