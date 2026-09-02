from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.db.base import session_scope
from app.db.models import JobLease, WorkerRegistration

_WORKER_ID = None
_WORKER_TYPE = "celery"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def this_worker_id() -> str:
    """Stable per container/host. Celery prefork spawns child processes with
    different PIDs; keying on the PID gave every child its own registration and
    left the one created at `worker_ready` to go stale. One logical worker per
    container -> one registration everyone keeps fresh. Override with
    ACF_WORKER_ID for multiple workers on one host."""
    global _WORKER_ID
    if _WORKER_ID is None:
        _WORKER_ID = os.environ.get("ACF_WORKER_ID") or socket.gethostname()
    return _WORKER_ID


def _upsert(s, *, worker_type: str, status: str, current_job: str | None) -> WorkerRegistration:
    wid = this_worker_id()
    row = s.get(WorkerRegistration, wid)
    if row is None:
        row = WorkerRegistration(id=wid, worker_type=worker_type,
                                 hostname=socket.gethostname(),
                                 version=get_settings().app_version,
                                 started_at=_now())
        s.add(row)
    row.worker_type = worker_type
    # the id is stable across container rebuilds; keep the descriptive fields
    # pointing at the running container / current build, not the first one seen.
    row.hostname = socket.gethostname()
    row.version = get_settings().app_version
    row.last_heartbeat = _now()
    row.status = status
    row.current_job = current_job
    return row


def register_worker(worker_type: str) -> str:
    global _WORKER_TYPE
    _WORKER_TYPE = worker_type or _WORKER_TYPE
    with session_scope() as s:
        wid = this_worker_id()
        # a fresh start supersedes any prior registration from this host
        # (e.g. an old PID-keyed row from before the id scheme changed)
        for old in s.query(WorkerRegistration).filter(
                WorkerRegistration.hostname == socket.gethostname(),
                WorkerRegistration.id != wid).all():
            s.delete(old)
        _upsert(s, worker_type=_WORKER_TYPE, status="HEALTHY", current_job=None)
    return wid


def heartbeat(current_job: str | None = None, status: str = "HEALTHY") -> None:
    with session_scope() as s:
        # upsert — a prefork child that never saw `worker_ready` still keeps the
        # container's registration fresh instead of no-op'ing on a missing row.
        _upsert(s, worker_type=_WORKER_TYPE, status=status, current_job=current_job)
        for lease in s.query(JobLease).filter_by(worker_id=this_worker_id(), released=False):
            lease.heartbeat_at = _now()
            lease.lease_expires_at = _now() + timedelta(seconds=get_settings().job_lease_seconds)


def worker_states() -> list[dict]:
    s_cfg = get_settings()
    stale_cut = _now() - timedelta(seconds=s_cfg.worker_heartbeat_stale_s)
    dead_cut = _now() - timedelta(seconds=s_cfg.worker_heartbeat_stale_s * 4)
    out = []
    with session_scope() as s:
        for w in s.query(WorkerRegistration).all():
            hb = w.last_heartbeat.replace(tzinfo=timezone.utc) if w.last_heartbeat.tzinfo is None \
                else w.last_heartbeat
            status = w.status
            if hb < dead_cut:
                status = "DEAD"
            elif hb < stale_cut:
                status = "STALE"
            out.append({"worker_id": w.id, "type": w.worker_type, "hostname": w.hostname,
                        "version": w.version, "status": status,
                        "current_job": w.current_job,
                        "last_heartbeat": w.last_heartbeat.isoformat(),
                        "started_at": w.started_at.isoformat()})
    return out


# ---- leases -------------------------------------------------------------- #

class LeaseNotAcquired(RuntimeError):
    pass


def acquire_lease(job_kind: str, job_id: str) -> str | None:
    """Return the lease id, or None if another live worker already holds it.
    Duplicate-execution guard: two workers cannot both hold an active lease
    (DB unique on (job_kind, job_id, released=False))."""
    wid = this_worker_id()
    ttl = get_settings().job_lease_seconds
    with session_scope() as s:
        # reclaim an expired lease
        existing = (s.query(JobLease)
                    .filter_by(job_kind=job_kind, job_id=job_id, released=False).first())
        if existing:
            exp = existing.lease_expires_at
            exp = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
            if exp > _now() and existing.worker_id != wid:
                return None                      # still held by a live worker
            existing.released = True
            existing.outcome = "RECOVERED"
            s.flush()
        lease = JobLease(job_kind=job_kind, job_id=job_id, worker_id=wid,
                         acquired_at=_now(), heartbeat_at=_now(),
                         lease_expires_at=_now() + timedelta(seconds=ttl))
        s.add(lease)
        try:
            s.flush()
        except Exception:  # unique violation -> lost the race
            return None
        return lease.id


def release_lease(lease_id: str, outcome: str = "DONE") -> None:
    with session_scope() as s:
        row = s.get(JobLease, lease_id)
        if row and not row.released:
            row.released = True
            row.outcome = outcome


def scan_stuck_jobs() -> list[dict]:
    """Expired, unreleased leases => the worker died mid-job."""
    stuck = []
    with session_scope() as s:
        for lease in s.query(JobLease).filter_by(released=False):
            exp = lease.lease_expires_at
            exp = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
            if exp < _now():
                lease.released = True
                lease.outcome = "STUCK"
                stuck.append({"lease_id": lease.id, "job_kind": lease.job_kind,
                              "job_id": lease.job_id, "worker_id": lease.worker_id})
    if stuck:
        from app.ops.alerts import raise_alert

        raise_alert("HIGH", "stuck_jobs", f"{len(stuck)} stuck job(s) recovered",
                    {"jobs": stuck[:10]})
    return stuck
