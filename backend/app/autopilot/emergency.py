from __future__ import annotations

from datetime import datetime, timezone

from app.config import get_settings
from app.db.models import AutopilotRun, PublishJob, TopicCandidate

# PAUSE: let in-flight work finish, start nothing new.
# STOP : additionally hold everything pending/queued that we still can.


def emergency_stop(session, *, actor: str = "user") -> dict:
    s = get_settings()
    s.autopilot_emergency_stop = True                       # in-process hint
    # persistent, survives restart (Phase 5 §67)
    from app.ops.runtime_flags import FLAG_EMERGENCY_STOP, set_flag

    set_flag(FLAG_EMERGENCY_STOP, {"enabled": True, "by": actor}, actor=actor)
    held_runs = held_candidates = held_jobs = 0

    for run in session.query(AutopilotRun).filter(AutopilotRun.status.in_(["RUNNING", "HOLD", "PAUSED"])):
        run.status = "STOPPED"
        run.pause_reason = f"emergency stop by {actor}"
        run.finished_at = datetime.now(timezone.utc)
        held_runs += 1

    for cand in session.query(TopicCandidate).filter(
        TopicCandidate.status.in_(["SELECTED", "PRODUCING", "SCORED", "SCHEDULED"])
    ):
        cand.status = "CANCELLED"
        cand.explanation = {**(cand.explanation or {}), "cancel_reason": ["emergency stop"]}
        held_candidates += 1

    # hold publish jobs that haven't left our side yet (Phase 2: never touch a job
    # already UPLOADING/PROCESSING/PUBLISHING on the remote platform)
    for job in session.query(PublishJob).filter(
        PublishJob.status.in_(["READY", "SCHEDULED", "QUEUED", "DRAFT", "WAITING_APPROVAL", "RETRY"])
    ):
        job.status = "CANCELLED"
        job.last_error_message = "autopilot emergency stop"
        held_jobs += 1

    session.flush()
    return {"stopped": True, "held_runs": held_runs, "held_candidates": held_candidates,
            "held_jobs": held_jobs}


def resume_after_stop(session, *, actor: str = "user") -> dict:
    s = get_settings()
    s.autopilot_emergency_stop = False
    from app.ops.runtime_flags import FLAG_EMERGENCY_STOP, set_flag

    set_flag(FLAG_EMERGENCY_STOP, {"enabled": False, "by": actor}, actor=actor)
    return {"resumed": True, "by": actor}


def pause_run(session, run_id: str, reason: str) -> dict:
    run = session.get(AutopilotRun, run_id)
    if run is None:
        return {"ok": False, "reason": "run not found"}
    run.status = "PAUSED"
    run.pause_reason = reason
    session.flush()
    return {"ok": True, "run_id": run_id, "status": "PAUSED", "reason": reason}


def resume_run(session, run_id: str) -> dict:
    run = session.get(AutopilotRun, run_id)
    if run is None or run.status != "PAUSED":
        return {"ok": False, "reason": "not paused"}
    run.status = "RUNNING"
    run.pause_reason = None
    session.flush()
    return {"ok": True, "run_id": run_id, "status": "RUNNING"}
