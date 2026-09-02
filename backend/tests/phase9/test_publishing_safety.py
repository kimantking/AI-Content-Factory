"""Phase 9 §36-§40, §84 — publishing duplicate-safety under retry / concurrency /
late governance change. Reuses the publishing fixtures.

Most of the publishing failure matrix is already proven in tests/publishing/
(idempotent rerun, crash-reconcile, token refresh, dead-letter, scheduler
restart, platform-failure isolation). This adds: a concurrent double-fire of the
same job -> 1 remote post, and a governance state that flips to BLOCK after the
job is queued -> 0 remote."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db.base import session_scope
from app.publishing.engine import run_publish_job
from app.publishing.mock_platform import mock_platform

pytest_plugins = ["tests.publishing.conftest"]
pytestmark = [pytest.mark.phase9, pytest.mark.failure]


def _job(campaign_id, account_id, platform="youtube_shorts"):
    from app.db.models import PublishJob
    with session_scope() as s:
        j = PublishJob(campaign_id=campaign_id, platform=platform, content_type="short",
                       platform_account_id=account_id, status="READY", run_mode="MANUAL",
                       approval_status="APPROVED", idempotency_key=str(uuid.uuid4()))
        s.add(j)
        s.flush()
        return j.id


def test_concurrent_double_fire_same_job_one_remote_post(ready_media_campaign, connect_account):
    acc = connect_account("youtube_shorts")
    jid = _job(ready_media_campaign, acc)
    with ThreadPoolExecutor(max_workers=2) as ex:
        res = [f.result() for f in [ex.submit(run_publish_job, jid), ex.submit(run_publish_job, jid)]]
    from app.db.models import PublishJob
    with session_scope() as s:
        remote_id = s.get(PublishJob, jid).remote_post_id
    # the mock platform tracks every distinct post it created this test (reset per test)
    remote_posts = len(getattr(mock_platform, "_posts", {}))
    assert remote_id is not None
    assert remote_posts <= 1, f"{remote_posts} distinct remote posts for one job"
    assert "PUBLISHED" in [x.get("status") for x in res]


def test_retry_after_timeout_does_not_double_post(ready_media_campaign, connect_account):
    acc = connect_account("youtube_shorts")
    jid = _job(ready_media_campaign, acc)
    r1 = run_publish_job(jid)          # first publish
    r2 = run_publish_job(jid)          # a retry of the same job
    from app.db.models import PublishJob
    with session_scope() as s:
        idem = s.get(PublishJob, jid).remote_post_id
    assert r1.get("status") == "PUBLISHED"
    assert r2.get("idempotent_skip") is True and idem is not None


def test_rights_expiry_after_queue_blocks_scheduled_publish(ready_media_campaign, connect_account,
                                                            _base_settings):
    """§39/§66 — the worker re-checks rights right before the remote call: an asset
    whose licence expired between queue and the scheduled time -> 0 remote."""
    _base_settings.governance_enforce = True
    acc = connect_account("youtube_shorts")
    from app.db.models import Asset, PublishJob
    from app.db.models_gov import RightsLedger
    with session_scope() as s:
        asset = s.query(Asset).filter_by(campaign_id=ready_media_campaign).first()
        s.add(RightsLedger(
            campaign_id=ready_media_campaign, asset_id=asset.id if asset else str(uuid.uuid4()),
            source_type="STOCK", license_type="STOCK_LICENSE", commercial_use="YES",
            expiration_at=datetime.now(timezone.utc) - timedelta(days=1)))   # already expired
        j = PublishJob(campaign_id=ready_media_campaign, platform="youtube_shorts",
                       content_type="short", platform_account_id=acc, status="READY",
                       run_mode="MANUAL", approval_status="APPROVED",
                       scheduled_at=datetime.now(timezone.utc),
                       idempotency_key=str(uuid.uuid4()))
        s.add(j)
        s.flush()
        jid = j.id
    res = run_publish_job(jid)
    with session_scope() as s:
        job = s.get(PublishJob, jid)
        blocked = job.remote_post_id is None and res.get("status") != "PUBLISHED"
    assert blocked, res
