from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import session_scope
from app.db.models import Campaign, PublishJob
from app.publishing.engine import run_publish_job
from app.publishing.mock_platform import mock_platform
from app.publishing.scheduler import due_jobs, schedule_job
from app.publishing.service import create_jobs_for_campaign

pytestmark = pytest.mark.integration


def test_crash_between_remote_success_and_db_save_is_reconciled(ready_media_campaign, connect_account):
    cid = ready_media_campaign
    with session_scope() as s:
        jobs = create_jobs_for_campaign(
            s, cid, accounts={"youtube_shorts": connect_account("youtube_shorts")},
            run_mode="MANUAL", dry_run=False)
        job = next(j for j in jobs if j.platform == "youtube_shorts")
        jid, key = job.id, job.idempotency_key

    # simulate: the platform already created the post, but the worker crashed
    # before writing remote_post_id. Seed the mock platform's idempotency index.
    cnt = mock_platform.create_container("youtube", key, {"seed": True})
    seeded = mock_platform.publish_container("youtube", cnt, key)
    posts_before = len(mock_platform._posts)

    with session_scope() as s:
        j = s.get(PublishJob, jid)
        j.status = "PUBLISHING"          # stuck mid-flight, no remote id
        j.remote_post_id = None

    res = run_publish_job(jid)
    assert res["status"] == "PUBLISHED"
    assert res["remote_post_id"] == seeded.remote_post_id       # adopted, not re-posted
    assert len(mock_platform._posts) == posts_before            # NO duplicate post


def test_rate_limit_sets_retry_then_recovers(ready_media_campaign, connect_account):
    cid = ready_media_campaign
    jid = _one_job(cid, connect_account, "youtube_shorts")

    mock_platform.set_scenario("RATE_LIMIT", "youtube")
    r1 = run_publish_job(jid)
    assert r1["status"] == "RETRY"
    with session_scope() as s:
        j = s.get(PublishJob, jid)
        assert j.next_retry_at is not None and j.attempt_count == 1
        assert j.dead_lettered is False

    mock_platform.clear_scenarios()
    r2 = run_publish_job(jid)
    assert r2["status"] == "PUBLISHED"


def test_policy_rejection_is_blocked_no_retry(ready_media_campaign, connect_account):
    cid = ready_media_campaign
    jid = _one_job(cid, connect_account, "youtube_shorts")
    mock_platform.set_scenario("POLICY_REJECTED", "youtube")
    r = run_publish_job(jid)
    assert r["status"] == "BLOCKED"
    with session_scope() as s:
        assert s.get(PublishJob, jid).next_retry_at is None


def test_repeated_failure_dead_letters(ready_media_campaign, connect_account, _base_settings):
    _base_settings.publish_max_attempts = 2
    cid = ready_media_campaign
    jid = _one_job(cid, connect_account, "youtube_shorts", max_attempts=2)
    mock_platform.set_scenario("NETWORK_TIMEOUT", "youtube")
    run_publish_job(jid)
    run_publish_job(jid)
    with session_scope() as s:
        j = s.get(PublishJob, jid)
        assert j.dead_lettered is True and j.status == "FAILED"
    # a dead-lettered job is not retried
    r = run_publish_job(jid)
    assert r.get("dead_lettered") is True


def test_token_expired_refreshes_and_publishes(ready_media_campaign, connect_account):
    cid = ready_media_campaign
    aid = connect_account("youtube_shorts")
    jid = _one_job(cid, connect_account, "youtube_shorts", account_id=aid)
    mock_platform.set_scenario("TOKEN_EXPIRED", "youtube")

    r1 = run_publish_job(jid)              # publish raises TOKEN_EXPIRED -> RETRY
    assert r1["status"] == "RETRY"
    mock_platform.clear_scenarios()
    r2 = run_publish_job(jid)
    assert r2["status"] == "PUBLISHED"


def test_scheduler_survives_restart(ready_media_campaign, connect_account):
    cid = ready_media_campaign
    aid = connect_account("youtube_shorts")
    with session_scope() as s:
        job = create_jobs_for_campaign(s, cid, accounts={"youtube_shorts": aid},
                                       run_mode="MANUAL", dry_run=False)
        j = next(x for x in job if x.platform == "youtube_shorts")
        schedule_job(s, j, datetime.now() - timedelta(minutes=1), "Asia/Seoul")
        jid = j.id

    # "restart": brand-new session, scheduler reads state purely from the DB
    with session_scope() as s:
        due = [d.id for d in due_jobs(s)]
    assert jid in due
    res = run_publish_job(jid)
    assert res["status"] == "PUBLISHED"


def _one_job(cid, connect_account, platform, *, account_id=None, max_attempts=5) -> str:
    with session_scope() as s:
        jobs = create_jobs_for_campaign(
            s, cid, accounts={platform: account_id or connect_account("youtube_shorts")},
            run_mode="MANUAL", dry_run=False)
        j = next(x for x in jobs if x.platform == platform)
        j.max_attempts = max_attempts
        return j.id
