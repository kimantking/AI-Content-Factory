from __future__ import annotations

from app.celery_app import celery_app
from app.agents.runner import run_pipeline
from app.agents.media_runner import run_media_pipeline
from app.db.base import session_scope
from app.db.models import Campaign, ErrorLog
from app.providers.errors import NON_RETRYABLE


_AUTO_MEDIA_MODES = {"CREATE_ONLY", "CREATE_AND_LEARN"}


def _enqueue_media_after_text(campaign_id: str, platforms: list[str] | None) -> bool:
    """Move a completed production campaign into the media queue exactly once."""
    with session_scope() as session:
        camp = session.get(Campaign, campaign_id)
        if (
            camp is None
            or camp.execution_mode not in _AUTO_MEDIA_MODES
            or camp.status != "SUCCESS"
            or camp.current_step != "done"
        ):
            return False
        selected_platforms = platforms or camp.platforms or ["youtube_shorts"]
        # Claim the hand-off before touching Celery so a refresh/retry cannot
        # enqueue the same render twice.
        camp.status = "RUNNING"
        camp.current_step = "media:queued"

    from app.config import get_settings

    if get_settings().run_inline:
        run_media_task.apply(args=[campaign_id, selected_platforms])
    else:
        try:
            run_media_task.apply_async(args=[campaign_id, selected_platforms], queue="render")
        except Exception:  # broker unavailable -> preserve the existing local fallback
            run_media_task.apply(args=[campaign_id, selected_platforms])
    return True


def _mark_failed(campaign_id: str, exc: Exception) -> None:
    with session_scope() as session:
        camp = session.get(Campaign, campaign_id)
        etype = getattr(exc, "error_type", type(exc).__name__)
        if camp:
            camp.status = "FAILED"
            camp.error_message = f"{etype}: {exc}"[:2000]
        session.add(ErrorLog(campaign_id=campaign_id, scope="task",
                             error_type=etype, message=str(exc)[:2000]))


@celery_app.task(bind=True, name="run_campaign", max_retries=2, default_retry_delay=5)
def run_campaign_task(self, campaign_id: str, topic: str,
                      audience_goal: str = "BALANCED", platforms: list[str] | None = None,
                      resume: bool = False):
    try:
        state = run_pipeline(campaign_id, topic, audience_goal, platforms, resume=resume)
        media_started = _enqueue_media_after_text(campaign_id, platforms)
        return {
            "campaign_id": campaign_id,
            "status": "RUNNING" if media_started else state.get("status"),
            "media_started": media_started,
        }
    except Exception as exc:  # noqa: BLE001
        etype = getattr(exc, "error_type", type(exc).__name__)
        if etype in NON_RETRYABLE or self.request.retries >= self.max_retries:
            _mark_failed(campaign_id, exc)
            raise
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="run_media", queue="render", max_retries=2, default_retry_delay=5)
def run_media_task(self, campaign_id: str, platforms: list[str] | None = None, resume: bool = False):
    try:
        state = run_media_pipeline(
            campaign_id, platforms, resume=resume or self.request.retries > 0,
        )
        return {"campaign_id": campaign_id, "status": state.get("status")}
    except Exception as exc:  # noqa: BLE001
        etype = getattr(exc, "error_type", type(exc).__name__)
        if etype in NON_RETRYABLE or self.request.retries >= self.max_retries:
            _mark_failed(campaign_id, exc)
            raise
        raise self.retry(exc=exc)


@celery_app.task(name="run_publish_job", queue="publish")
def run_publish_job_task(job_id: str):
    from app.publishing.engine import run_publish_job

    return run_publish_job(job_id)


@celery_app.task(name="collect_analytics", queue="analytics")
def collect_analytics_task(analytics_job_id: str):
    """Process one AnalyticsJob. A platform/metric failure marks THIS job, never
    a sibling (platform isolation)."""
    from datetime import datetime, timezone

    from app.analytics.performance import compute_performance_score
    from app.analytics.snapshot import collect_snapshot
    from app.config import get_settings
    from app.db.models import AnalyticsJob

    with session_scope() as session:
        job = session.get(AnalyticsJob, analytics_job_id)
        if job is None:
            return {"analytics_job_id": analytics_job_id, "status": "MISSING"}
        if job.status == "SUCCESS":
            return {"analytics_job_id": analytics_job_id, "status": "SUCCESS", "idempotent": True}
        job.status = "RUNNING"
        job.attempts += 1
        job.started_at = datetime.now(timezone.utc)
        pub_id, window = job.publication_id, job.window_label

    try:
        with session_scope() as session:
            snap = collect_snapshot(session, pub_id, window)
            status = {"SUCCESS": "SUCCESS", "PARTIAL": "PARTIAL",
                      "UNAVAILABLE": "UNAVAILABLE", "FAILED": "FAILED"}.get(
                          snap.collection_status, "PARTIAL")
            compute_performance_score(session, pub_id, get_settings().default_objective)
        with session_scope() as session:
            j = session.get(AnalyticsJob, analytics_job_id)
            j.status = status
            j.finished_at = datetime.now(timezone.utc)
        return {"analytics_job_id": analytics_job_id, "status": status}
    except Exception as exc:  # noqa: BLE001
        with session_scope() as session:
            j = session.get(AnalyticsJob, analytics_job_id)
            if j:
                j.status = "RETRY" if j.attempts < 4 else "FAILED"
                j.last_error = str(exc)[:2000]
        return {"analytics_job_id": analytics_job_id, "status": "RETRY", "error": str(exc)[:200]}


@celery_app.task(name="analytics_scheduler_tick", queue="analytics")
def analytics_scheduler_tick():
    from app.analytics.schedule import due_analytics_jobs

    ids: list[str] = []
    with session_scope() as session:
        for job in due_analytics_jobs(session):
            job.status = "QUEUED" if job.status == "SCHEDULED" else job.status
            ids.append(job.id)
    for jid in ids:
        try:
            collect_analytics_task.apply_async(args=[jid], queue="analytics")
        except Exception:  # noqa: BLE001
            collect_analytics_task.apply(args=[jid])
    return {"enqueued": ids}


@celery_app.task(name="daily_learning", queue="analytics")
def daily_learning_task(run_date: str | None = None):
    from app.learning.reports import daily_learning_run

    with session_scope() as session:
        run = daily_learning_run(session, run_date)
        return {"run_date": run.run_date, "summary": run.summary}


@celery_app.task(name="autopilot_run", queue="autopilot")
def autopilot_run_task(mode: str | None = None, trigger: str = "schedule",
                       resume_run_id: str | None = None):
    from app.autopilot.controller import run_autopilot

    return run_autopilot(mode, trigger=trigger, resume_run_id=resume_run_id)


@celery_app.task(name="autopilot_breakout_watch", queue="autopilot")
def autopilot_breakout_watch():
    """Extra scan (mid-day / evening). Only escalates if a fresh BREAKOUT clears
    the threshold; SHADOW-level compute, never publishes on its own."""
    from app.autopilot.controller import run_autopilot

    return run_autopilot("SHADOW", trigger="breakout")


@celery_app.task(name="autopilot_calibration", queue="autopilot")
def autopilot_calibration_task():
    from app.autopilot.calibration import calibrate

    with session_scope() as session:
        return calibrate(session)


# ---- Phase 5 ops tasks ------------------------------------------------- #

@celery_app.task(name="ops_stuck_job_scan", queue="celery")
def ops_stuck_job_scan():
    from app.ops.worker_registry import scan_stuck_jobs

    return {"recovered": scan_stuck_jobs()}


@celery_app.task(name="ops_worker_heartbeat", queue="celery")
def ops_worker_heartbeat():
    from app.ops.worker_registry import heartbeat

    heartbeat()
    return {"ok": True}


@celery_app.task(name="ops_daily_backup", queue="celery")
def ops_daily_backup():
    from app.ops.backup import run_backup, verify_backup

    full = run_backup("full")
    v = verify_backup(full["backup_id"])
    run_backup("storage")
    return {"full": full["backup_id"], "verified": v.get("ok")}


@celery_app.task(name="publish_scheduler_tick", queue="publish")
def publish_scheduler_tick():
    """Enqueue every due PublishJob. Safe to run on a beat; DB-backed so a
    restart of backend/worker/beat loses no schedule."""
    from app.db.base import session_scope as _ss
    from app.publishing.base import PublishStatus
    from app.publishing.scheduler import due_jobs

    enqueued: list[str] = []
    with _ss() as session:
        for job in due_jobs(session):
            job.status = PublishStatus.QUEUED.value
            enqueued.append(job.id)
    for jid in enqueued:
        try:
            run_publish_job_task.apply_async(args=[jid], queue="publish")
        except Exception:  # noqa: BLE001
            run_publish_job_task.apply(args=[jid])
    return {"enqueued": enqueued}
