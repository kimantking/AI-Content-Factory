from __future__ import annotations

from celery import Celery

from app.config import get_settings

_s = get_settings()

celery_app = Celery(
    "acf",
    broker=_s.redis_url,
    backend=_s.redis_url,
    include=["app.tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    task_default_queue="celery",
    # Phase 1-B media queues. Scene-level image/video/audio tasks (added when a
    # real provider is wired) route here; render is isolated so heavy ffmpeg jobs
    # don't starve quick generations.
    task_routes={
        "run_media": {"queue": "render"},
        "gen_image": {"queue": "image"},
        "gen_video": {"queue": "video"},
        "gen_audio": {"queue": "audio"},
        "run_publish_job": {"queue": "publish"},
        "publish_scheduler_tick": {"queue": "publish"},
        "collect_analytics": {"queue": "analytics"},
        "analytics_scheduler_tick": {"queue": "analytics"},
        "daily_learning": {"queue": "analytics"},
        "autopilot_run": {"queue": "autopilot"},
        "autopilot_breakout_watch": {"queue": "autopilot"},
        "autopilot_calibration": {"queue": "autopilot"},
    },
    beat_schedule={
        "publish-scheduler-tick": {"task": "publish_scheduler_tick", "schedule": 30.0},
        "analytics-scheduler-tick": {"task": "analytics_scheduler_tick", "schedule": 300.0},
        "daily-learning": {"task": "daily_learning", "schedule": 86400.0},
        "autopilot-daily": {"task": "autopilot_run", "schedule": 86400.0},
        "autopilot-breakout-watch": {"task": "autopilot_breakout_watch", "schedule": 21600.0},
        "autopilot-calibration": {"task": "autopilot_calibration", "schedule": 86400.0},
        "ops-stuck-job-scan": {"task": "ops_stuck_job_scan", "schedule": 120.0},
        "ops-heartbeat": {"task": "ops_worker_heartbeat", "schedule": 30.0},
        "ops-daily-backup": {"task": "ops_daily_backup", "schedule": 86400.0},
    },
    worker_send_task_events=True,
    worker_hijack_root_logger=False,
)
celery_app.set_current()


# --- Phase 5: worker lifecycle -------------------------------------------- #
try:
    from celery.signals import (  # noqa: E402
        task_postrun,
        task_prerun,
        worker_ready,
        worker_shutdown,
    )

    @worker_ready.connect
    def _on_ready(**_kw):
        try:
            from app.ops.logging_config import configure_logging
            from app.ops.worker_registry import register_worker

            configure_logging()
            register_worker("celery")
        except Exception:  # noqa: BLE001
            pass

    @task_prerun.connect
    def _on_prerun(task_id=None, task=None, **_kw):
        try:
            from app.ops.worker_registry import heartbeat

            heartbeat(current_job=str(task_id), status="BUSY")
        except Exception:  # noqa: BLE001
            pass

    @task_postrun.connect
    def _on_postrun(**_kw):
        try:
            from app.ops.worker_registry import heartbeat

            heartbeat(current_job=None, status="HEALTHY")
        except Exception:  # noqa: BLE001
            pass

    @worker_shutdown.connect
    def _on_shutdown(**_kw):
        """Graceful: release any lease this worker holds so nothing is stuck
        forever, and mark the worker DEAD."""
        try:
            from app.db.base import session_scope
            from app.db.models import JobLease, WorkerRegistration
            from app.ops.worker_registry import this_worker_id

            wid = this_worker_id()
            with session_scope() as s:
                for lease in s.query(JobLease).filter_by(worker_id=wid, released=False):
                    lease.released = True
                    lease.outcome = "RECOVERED"
                w = s.get(WorkerRegistration, wid)
                if w:
                    w.status = "DEAD"
        except Exception:  # noqa: BLE001
            pass
except Exception:  # noqa: BLE001 — signals unavailable in some contexts
    pass

ALL_QUEUES = ("celery", "image", "video", "audio", "render", "publish", "analytics", "autopilot")
