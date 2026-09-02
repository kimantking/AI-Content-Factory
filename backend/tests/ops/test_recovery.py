from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import session_scope
from app.db.models import DeadLetter, JobLease, OpsAlert, WorkerRegistration
from app.ops.dlq import dead_letter, list_dlq, resolve_dlq, retry_from_dlq
from app.ops import worker_registry as wr

pytestmark = pytest.mark.integration


def test_worker_register_heartbeat_and_stale(_ops_defaults):
    _ops_defaults.worker_heartbeat_stale_s = 1
    wid = wr.register_worker("media")
    states = {w["worker_id"]: w for w in wr.worker_states()}
    assert states[wid]["status"] == "HEALTHY"
    # backdate the heartbeat -> STALE / DEAD
    with session_scope() as s:
        s.get(WorkerRegistration, wid).last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=5)
    assert {w["worker_id"]: w for w in wr.worker_states()}[wid]["status"] in ("STALE", "DEAD")


def test_job_lease_prevents_duplicate_execution():
    lease = wr.acquire_lease("render", "job-1")
    assert lease is not None
    # a "second worker" tries the same job
    wr._WORKER_ID = "other-worker:1:abc"
    try:
        assert wr.acquire_lease("render", "job-1") is None      # blocked, still held
    finally:
        wr._WORKER_ID = None
    wr.release_lease(lease, "DONE")
    assert wr.acquire_lease("render", "job-1") is not None       # now free


def test_expired_lease_is_reclaimed_and_flagged_stuck():
    lease = wr.acquire_lease("media", "job-stuck")
    with session_scope() as s:
        s.get(JobLease, lease).lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    stuck = wr.scan_stuck_jobs()
    assert any(x["job_id"] == "job-stuck" for x in stuck)
    with session_scope() as s:
        assert s.query(OpsAlert).filter_by(key="stuck_jobs").count() >= 1
    # after recovery the job can be leased again
    assert wr.acquire_lease("media", "job-stuck") is not None


def test_dlq_lifecycle_and_non_retryable_guard(_ops_defaults):
    _ops_defaults.run_inline = True
    did = dead_letter("publish", "pj-1", reason="max attempts",
                      error_type="PROVIDER_ERROR", attempts=5)
    rows = list_dlq("OPEN")
    assert any(r["id"] == did and r["retryable"] for r in rows)

    auth_id = dead_letter("publish", "pj-2", reason="revoked",
                          error_type="AUTH_REVOKED", attempts=1)
    r = retry_from_dlq(auth_id)
    assert r["ok"] is False and "retryable" in r["reason"]

    ok = retry_from_dlq(did)
    assert ok["ok"] is True
    with session_scope() as s:
        assert s.get(DeadLetter, did).status == "RETRIED"

    assert resolve_dlq(auth_id, status="CANCELLED") is True
    with session_scope() as s:
        assert s.get(DeadLetter, auth_id).status == "CANCELLED"
