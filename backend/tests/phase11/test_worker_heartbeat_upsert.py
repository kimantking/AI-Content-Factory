"""Local-runtime repair — the Celery worker's DB heartbeat.

Bug: `ops_worker_heartbeat` runs in a prefork child with a different PID than the
process that ran `worker_ready` -> `heartbeat()` did `s.get(id)` -> None -> no-op,
so the registration went stale and the AI Support Snapshot showed
"Workers/Scheduler DEGRADED" even though the worker was fine.

Fix: `this_worker_id()` is stable per container (hostname / ACF_WORKER_ID, not
PID) and `heartbeat()` upserts.
"""
from __future__ import annotations

import pytest

from app.db.base import session_scope
from app.db.models import WorkerRegistration
from app.ops import worker_registry as wr

pytestmark = [pytest.mark.phase11, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _reset_worker_id():
    wr._WORKER_ID = None
    yield
    wr._WORKER_ID = None


def test_heartbeat_creates_registration_when_missing():
    """A heartbeat from a process that never saw worker_ready still registers."""
    with session_scope() as s:
        assert s.query(WorkerRegistration).count() == 0
    wr.heartbeat(status="HEALTHY")
    states = wr.worker_states()
    assert len(states) == 1 and states[0]["status"] == "HEALTHY"


def test_worker_id_is_stable_across_calls_and_honours_env(monkeypatch):
    monkeypatch.setenv("ACF_WORKER_ID", "acf-worker-test")
    wr._WORKER_ID = None
    a = wr.this_worker_id()
    b = wr.this_worker_id()
    assert a == b == "acf-worker-test"
    # no PID in the id -> a forked child computes the same id
    assert ":" not in a.split("acf-worker")[0] if "acf-worker" in a else True


def test_register_then_heartbeat_keeps_one_fresh_row():
    wid = wr.register_worker("celery")
    # simulate a child heartbeat (same container id)
    wr._WORKER_ID = None
    wr.heartbeat(status="BUSY", current_job="job-123")
    states = {w["worker_id"]: w for w in wr.worker_states()}
    assert list(states) == [wid]
    assert states[wid]["status"] == "BUSY" and states[wid]["current_job"] == "job-123"


def test_register_supersedes_a_stale_row_from_the_same_host():
    import socket
    with session_scope() as s:
        s.add(WorkerRegistration(id=f"{socket.gethostname()}:9999:deadbe", worker_type="celery",
                                 hostname=socket.gethostname(), version="old"))
    wr.register_worker("celery")
    with session_scope() as s:
        ids = [r.id for r in s.query(WorkerRegistration).all()]
    assert ids == [wr.this_worker_id()]
