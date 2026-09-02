from __future__ import annotations

from datetime import datetime, timezone

from app.db.base import session_scope
from app.db.models import DeadLetter

# error types that must NOT be blindly retried from the DLQ UI
_NON_RETRYABLE = {"AUTH_ERROR", "AUTH_REVOKED", "PERMISSION_MISSING",
                  "POLICY_REJECTION", "BUDGET_EXCEEDED", "DUPLICATE"}


def dead_letter(job_kind: str, job_id: str, *, reason: str, error_type: str | None = None,
                last_error: str | None = None, attempts: int = 0,
                campaign_id: str | None = None, payload: dict | None = None) -> str:
    with session_scope() as s:
        existing = (s.query(DeadLetter)
                    .filter_by(job_kind=job_kind, job_id=job_id, status="OPEN").first())
        if existing:
            existing.attempts = attempts
            existing.last_error = last_error
            existing.updated_at = datetime.now(timezone.utc)
            return existing.id
        row = DeadLetter(job_kind=job_kind, job_id=job_id, reason=reason,
                         error_type=error_type, last_error=last_error, attempts=attempts,
                         campaign_id=campaign_id, payload=payload or {})
        s.add(row)
        s.flush()
        did = row.id
    from app.ops.alerts import raise_alert

    raise_alert("WARNING", "dead_letter", f"{job_kind} job dead-lettered: {reason}",
                {"job_id": job_id, "error_type": error_type})
    return did


def list_dlq(status: str = "OPEN", limit: int = 100) -> list[dict]:
    with session_scope() as s:
        rows = (s.query(DeadLetter).filter_by(status=status)
                .order_by(DeadLetter.created_at.desc()).limit(limit).all())
        return [{"id": r.id, "job_kind": r.job_kind, "job_id": r.job_id,
                 "campaign_id": r.campaign_id, "reason": r.reason,
                 "error_type": r.error_type, "attempts": r.attempts,
                 "retryable": r.error_type not in _NON_RETRYABLE,
                 "last_error": (r.last_error or "")[:300],
                 "created_at": r.created_at.isoformat()} for r in rows]


def retry_from_dlq(dlq_id: str, *, actor: str = "user") -> dict:
    with session_scope() as s:
        row = s.get(DeadLetter, dlq_id)
        if row is None:
            return {"ok": False, "reason": "not found"}
        if row.error_type in _NON_RETRYABLE:
            return {"ok": False, "reason": f"{row.error_type} is not retryable — resolve or fix first"}
        row.status = "RETRIED"
        kind, jid = row.job_kind, row.job_id
        from app.db.models import AuditEntry

        s.add(AuditEntry(action="dlq:retry", actor=actor,
                         resource_type=kind, resource_id=jid))

    # re-enqueue on the right task
    _requeue(kind, jid)
    return {"ok": True, "requeued": {"kind": kind, "job_id": jid}}


def resolve_dlq(dlq_id: str, *, actor: str = "user", status: str = "RESOLVED") -> bool:
    with session_scope() as s:
        row = s.get(DeadLetter, dlq_id)
        if row is None:
            return False
        row.status = status
        from app.db.models import AuditEntry

        s.add(AuditEntry(action=f"dlq:{status.lower()}", actor=actor,
                         resource_type=row.job_kind, resource_id=row.job_id))
    return True


def _requeue(kind: str, job_id: str) -> None:
    try:
        from app.tasks import (  # noqa: PLC0415
            collect_analytics_task,
            run_media_task,
            run_publish_job_task,
        )

        if kind == "publish":
            run_publish_job_task.apply_async(args=[job_id], queue="publish")
        elif kind == "analytics":
            collect_analytics_task.apply_async(args=[job_id], queue="analytics")
        elif kind == "media":
            run_media_task.apply_async(args=[job_id], queue="render")
    except Exception:  # noqa: BLE001 — broker down: leave as RETRIED, operator re-runs
        pass
