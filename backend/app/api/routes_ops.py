from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import get_db
from app.ops import health as _health
from app.ops.alerts import open_alerts, resolve_alert
from app.ops.backup import backup_status
from app.ops.dlq import list_dlq, resolve_dlq, retry_from_dlq
from app.ops.metrics import render_prometheus
from app.ops.runtime_flags import (
    FLAG_MAINTENANCE_MODE,
    FLAG_PAID_PROVIDER_PAUSE,
    FLAG_PUBLISH_PAUSE,
    FLAG_SAFE_MODE,
    all_flags,
    set_flag,
)
from app.ops.worker_registry import scan_stuck_jobs, worker_states

health_router = APIRouter(tags=["health"])
ops_router = APIRouter(prefix="/api/ops", tags=["ops"])


# ---- health (unauthenticated, cheap) ------------------------------------ #

@health_router.get("/health/live")
def live():
    return _health.liveness()


@health_router.get("/health/ready")
def ready(response: Response):
    r = _health.readiness()
    response.status_code = 200 if r["ready"] else 503
    return r


@health_router.get("/health/dependencies")
def deps():
    return _health.dependencies()


@health_router.get("/health")
def health_root(response: Response):
    r = _health.readiness()
    response.status_code = 200 if r["ready"] else 503
    return {"status": "ok" if r["ready"] else "degraded", "phase": "5",
            "version": get_settings().app_version, **r}


@health_router.get("/metrics")
def metrics():
    return Response(render_prometheus(), media_type="text/plain; version=0.0.4")


# ---- ops (admin) ------------------------------------------------------ #

@ops_router.get("/status")
def status(db: Session = Depends(get_db)):
    s = get_settings()
    return {
        "version": s.app_version, "env": s.app_env,
        "dependencies": _health.dependencies(),
        "workers": worker_states(),
        "flags": all_flags(),
        "backups": backup_status(),
        "open_alerts": open_alerts(limit=25),
        "dlq_open": len(list_dlq("OPEN", limit=200)),
    }


@ops_router.get("/deep-health")
def deep_health(force: bool = False):
    return _health.deep_health(force=force)


@ops_router.get("/config-check")
def config_check():
    """Phase 10 §3 — production config validation + per-capability status."""
    from app.ops.config_check import check_config

    return check_config()


@ops_router.get("/workers")
def workers():
    return worker_states()


@ops_router.post("/workers/scan-stuck")
def scan_stuck():
    return {"recovered": scan_stuck_jobs()}


@ops_router.get("/queues")
def queues():
    from app.ops.queue_backpressure import backpressure_state

    return backpressure_state()


@ops_router.get("/alerts")
def alerts():
    return open_alerts()


@ops_router.post("/alerts/{alert_id}/resolve")
def resolve(alert_id: str):
    if not resolve_alert(alert_id, actor="dashboard-user"):
        raise HTTPException(404, "alert not found")
    return {"ok": True}


@ops_router.get("/dlq")
def dlq(status: str = "OPEN"):
    return list_dlq(status)


@ops_router.post("/dlq/{dlq_id}/retry")
def dlq_retry(dlq_id: str):
    r = retry_from_dlq(dlq_id, actor="dashboard-user")
    if not r["ok"]:
        raise HTTPException(409, r["reason"])
    return r


@ops_router.post("/dlq/{dlq_id}/resolve")
def dlq_resolve(dlq_id: str, status: str = Body("RESOLVED", embed=True)):
    if not resolve_dlq(dlq_id, actor="dashboard-user", status=status):
        raise HTTPException(404, "not found")
    return {"ok": True}


@ops_router.post("/flags/{flag}")
def toggle_flag(flag: str, enabled: bool = Body(..., embed=True),
                confirm: bool = Body(False, embed=True)):
    flag = flag.upper()
    _toggleable = (FLAG_SAFE_MODE, FLAG_MAINTENANCE_MODE,
                   FLAG_PUBLISH_PAUSE, FLAG_PAID_PROVIDER_PAUSE)
    if flag not in _toggleable:
        raise HTTPException(400, f"toggleable flags: {', '.join(_toggleable)}")
    if enabled and not confirm:
        raise HTTPException(400, "confirm=true required to enable a mode")
    set_flag(flag, {"enabled": enabled}, actor="dashboard-user")
    return {"flag": flag, "enabled": enabled}


@ops_router.get("/backups")
def backups():
    return backup_status()


@ops_router.post("/backups/run")
def run_backup_endpoint(kind: str = Body("full", embed=True)):
    from app.ops.backup import run_backup

    return run_backup(kind)


@ops_router.post("/backups/{backup_id}/verify")
def verify_backup_endpoint(backup_id: str):
    from app.ops.backup import verify_backup

    return verify_backup(backup_id)


@ops_router.post("/cost-anomaly/check")
def cost_anomaly_check(campaign_id: str | None = Body(None, embed=True)):
    from app.ops.cost_anomaly import check_cost_anomaly

    return check_cost_anomaly(campaign_id=campaign_id)


@ops_router.post("/storage/integrity")
def storage_integrity():
    from app.ops.storage_integrity import scan_assets

    return scan_assets()


@ops_router.get("/_debug/boom")
def _debug_boom():
    """Non-production only: verifies the global error handler scrubs secrets."""
    if get_settings().is_production:
        raise HTTPException(404, "not found")
    raise RuntimeError(
        "leak check: token gAAAAAB" + "q" * 62 + " and Bearer abcdefghijklmnopqrst end"
    )
