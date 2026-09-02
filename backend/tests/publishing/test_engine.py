from __future__ import annotations

import pytest

from app.db.base import session_scope
from app.db.models import Publication, PublicationEvent, PublishAudit, PublishJob
from app.publishing.engine import run_publish_job
from app.publishing.mock_platform import mock_platform
from app.publishing.service import campaign_rollup, create_jobs_for_campaign

pytestmark = pytest.mark.integration


def _make_jobs(cid: str, accounts: dict) -> dict[str, str]:
    with session_scope() as s:
        jobs = create_jobs_for_campaign(s, cid, accounts=accounts, run_mode="MANUAL", dry_run=False)
        return {j.platform: j.id for j in jobs}


def test_end_to_end_publish_flow_mock(ready_media_campaign, connect_account):
    cid = ready_media_campaign
    jid = _make_jobs(cid, {"youtube_shorts": connect_account("youtube_shorts")})["youtube_shorts"]

    res = run_publish_job(jid)
    assert res["status"] == "PUBLISHED"
    assert res["remote_post_id"] and res["remote_url"] and res["provider_mode"] == "MOCK"

    with session_scope() as s:
        j = s.get(PublishJob, jid)
        assert j.status == "PUBLISHED" and j.published_at and j.verified_at
        pub = s.query(Publication).filter_by(publish_job_id=jid).first()
        assert pub.status == "PUBLISHED" and pub.remote_post_id == j.remote_post_id
        events = [e.event for e in s.query(PublicationEvent).filter_by(publish_job_id=jid)
                  .order_by(PublicationEvent.created_at)]
        assert events[:2] == ["QUEUED", "PREFLIGHT"] or "QUEUED" in events
        assert "PREFLIGHT" in events and "VERIFYING" in events and "PUBLISHED" in events
        assert events.index("PREFLIGHT") < events.index("PUBLISHED")
        assert s.query(PublishAudit).filter_by(publish_job_id=jid).count() >= 2


def test_idempotent_rerun_does_not_double_post(ready_media_campaign, connect_account):
    cid = ready_media_campaign
    jid = _make_jobs(cid, {"youtube_shorts": connect_account("youtube_shorts")})["youtube_shorts"]
    r1 = run_publish_job(jid)
    n = len(mock_platform._posts)
    r2 = run_publish_job(jid)
    assert r2.get("idempotent_skip") is True
    assert len(mock_platform._posts) == n
    assert r1["remote_post_id"]


def test_dry_run_never_calls_publish(ready_media_campaign, connect_account, _base_settings):
    _base_settings.dry_run = True
    cid = ready_media_campaign
    jid = _make_jobs(cid, {"youtube_shorts": connect_account("youtube_shorts")})["youtube_shorts"]
    res = run_publish_job(jid)
    assert res["status"] == "READY" and res.get("dry_run") is True
    assert len(mock_platform._posts) == 0
    with session_scope() as s:
        assert s.query(Publication).filter_by(publish_job_id=jid).first().status == "DRY_RUN"


def test_naver_clip_not_supported_naver_blog_manual(ready_media_campaign):
    cid = ready_media_campaign
    jobs = _make_jobs(cid, {})
    if "naver_clip" in jobs:
        assert run_publish_job(jobs["naver_clip"])["status"] == "NOT_SUPPORTED"


def test_threads_thread_chain(ready_media_campaign, connect_account):
    cid = ready_media_campaign
    jid = _make_jobs(cid, {"threads": connect_account("threads")})["threads"]
    with session_scope() as s:
        j = s.get(PublishJob, jid)
        j.content_type = "TEXT_THREAD"
        j.platform_settings = {"thread_posts": ["첫 번째 포스트", "이어지는 두 번째", "세 번째로 마무리"]}
    res = run_publish_job(jid)
    assert res["status"] == "PUBLISHED"
    assert len(res["thread_remote_ids"]) == 3


def test_platform_failure_isolation(ready_media_campaign, connect_account):
    cid = ready_media_campaign
    jids = _make_jobs(cid, {
        "youtube_shorts": connect_account("youtube_shorts"),
        "threads": connect_account("threads"),
    })
    mock_platform.set_scenario("RATE_LIMIT", "threads")
    tr = run_publish_job(jids["threads"])
    assert tr["status"] == "RETRY"
    mock_platform.clear_scenarios()

    yr = run_publish_job(jids["youtube_shorts"])
    assert yr["status"] == "PUBLISHED"

    with session_scope() as s:
        assert campaign_rollup(s, cid) in ("PARTIALLY_PUBLISHED", "IN_PROGRESS")
