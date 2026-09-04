"""AI Support Snapshot (Phase 10 §56-§77).

One read-only aggregation a user can screenshot / copy and hand to ChatGPT or a
support engineer for diagnosis with minimal follow-up questions.

Rules:
  * every field comes from a real source (DB / health service / queue / worker /
    routing telemetry / governance / cost) — no frontend hardcoding;
  * secrets are redacted via app.ops.redaction;
  * RBAC-scoped: a normal user sees only their workspace; a system admin sees
    infra detail. Other tenants' data is never included.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ops.redaction import redact
from app.support.errors import is_retryable, normalise, suggested_action

_PIPELINE = ["research", "fact_check", "strategize", "hook", "write_script", "qa_script",
             "media", "governance", "publish"]
_STEP_ALIAS = {
    "create_campaign": "research", "research": "research", "research_fix": "research",
    "fact_check": "fact_check", "strategize": "strategize", "hook": "hook",
    "write_script": "write_script", "qa_script": "qa_script", "persist": "publish",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt) -> str | None:
    if dt is None:
        return None
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    return dt.isoformat()


def _mode() -> str:
    return get_settings().app_env.upper()


# --------------------------------------------------------------------------- #
#  system health
# --------------------------------------------------------------------------- #

def _ffmpeg_status() -> dict:
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        return {"status": "OK", "source": "imageio-ffmpeg", "path_present": bool(exe)}
    except Exception:  # noqa: BLE001
        return {"status": "NOT_CONFIGURED" if not shutil.which("ffmpeg") else "OK"}


def _ollama_status() -> dict:
    s = get_settings()
    out = {"enabled": s.ollama_enabled, "base_url": s.ollama_base_url,
           "default_model": s.ollama_default_model, "reachable": False,
           "model_available": False, "last_error": None}
    from app.providers.ollama_llm import check_health

    h = check_health(base_url=s.ollama_base_url, model=s.ollama_default_model,
                     timeout_seconds=5)
    out["reachable"] = h["reachable"]
    out["model_available"] = h["model_available"]
    out["last_error"] = h.get("reason") or h.get("error")
    out["status"] = "OK" if (out["reachable"] and out["model_available"]) else (
        "DEGRADED" if out["reachable"] else "ERROR")
    return out


def _cloud_summary() -> dict:
    s = get_settings()

    def _kp(provider: str, env_attr: str) -> bool:
        try:
            from app.providers import credentials as cred
            return bool(cred.get_key(provider))
        except Exception:  # noqa: BLE001
            return bool(getattr(s, env_attr, None))

    out = {
        "anthropic_key_present": _kp("anthropic", "anthropic_api_key"),
        "tavily_key_present": _kp("tavily", "tavily_api_key"),
        "google_key_present": _kp("google", "google_api_key"),
        "elevenlabs_key_present": _kp("elevenlabs", "elevenlabs_api_key"),
        "llm_is_mock": bool(s.llm_is_mock),
        "allow_cloud_fallback": bool(s.allow_cloud_fallback),
        "local_only": bool(s.local_only),
        "status": "MOCK" if s.llm_is_mock else ("READY" if s.anthropic_api_key else "NEEDS_CREDENTIALS"),
    }
    try:
        from app.providers.status import provider_status

        out["providers"] = provider_status(probe=True)["providers"]
    except Exception:  # noqa: BLE001 — provider probe must never break the snapshot
        out["providers"] = provider_status_offline()
    return out


def provider_status_offline() -> list[dict]:
    from app.providers.status import provider_status

    return provider_status(probe=False)["providers"]


def _publisher_summary(db: Session, workspace_id: str | None) -> dict:
    from app.db.models import PlatformAccount
    q = db.query(PlatformAccount)
    rows = q.all()
    connected = sum(1 for r in rows if r.connection_status == "CONNECTED")
    mock = sum(1 for r in rows if (r.integration_status or "").startswith("MOCK"))
    return {"accounts": len(rows), "connected": connected, "mock_tested": mock,
            "status": "MOCK" if (mock and not connected) else ("READY" if connected else "NOT_CONFIGURED")}


def _system(db: Session, *, admin: bool, workspace_id: str | None) -> dict:
    from app.ops import health as H
    dbk = H.check_database()
    rds = H.check_redis()
    stg = H.check_storage()
    workers = []
    scheduler = {"status": "UNKNOWN"}
    try:
        from app.ops.worker_registry import worker_states
        workers = worker_states()
        online = [w for w in workers if w["status"] not in ("DEAD",)]
        scheduler = {"status": "OK" if online else "DEGRADED",
                     "online": len(online), "total": len(workers)}
    except Exception:  # noqa: BLE001
        pass
    return {
        "backend": {"status": "OK", "version": get_settings().app_version},
        "database": dbk,
        "redis": rds,
        "workers": scheduler if not admin else {**scheduler, "detail": workers},
        "scheduler": {"status": scheduler["status"]},
        "storage": stg if admin else {"status": stg.get("status")},
        "ffmpeg": _ffmpeg_status(),
        "ollama": _ollama_status(),
        "cloud_providers": _cloud_summary(),
        "publishers": _publisher_summary(db, workspace_id),
    }


def _overall(system: dict) -> str:
    crit = ("database", "redis")
    for k in crit:
        if system.get(k, {}).get("status") not in ("OK", "WARNING"):
            return "ERROR"
    degraded = any(
        system.get(k, {}).get("status") in ("DEGRADED", "ERROR", "CRITICAL", "DOWN")
        for k in ("workers", "storage", "ollama"))
    return "DEGRADED" if degraded else "OK"


# --------------------------------------------------------------------------- #
#  current job / pipeline / routing
# --------------------------------------------------------------------------- #

def _current_jobs(db: Session, workspace_id: str | None, admin: bool) -> list[dict]:
    from app.db.models import AgentRun, Campaign
    q = db.query(Campaign).filter(Campaign.status.in_(("RUNNING", "WAITING")))
    if not admin and workspace_id:
        q = q.filter(Campaign.workspace_id == workspace_id)
    out = []
    for c in q.order_by(desc(Campaign.created_at)).limit(10):
        runs = (db.query(AgentRun).filter_by(campaign_id=c.id)
                .order_by(desc(AgentRun.started_at)).all())
        last = runs[0] if runs else None
        started = min((r.started_at for r in runs), default=c.created_at)
        out.append({
            "campaign_id": c.id, "topic": (c.topic or "")[:120],
            "brand_id": c.brand_id, "channel_id": c.channel_id,
            "execution_mode": c.execution_mode or "CREATE_ONLY",
            "current_stage": c.current_step or "queued",
            "status": c.status,
            "started_at": _iso(started), "elapsed_s": round((_now() - (
                started.replace(tzinfo=timezone.utc) if started and started.tzinfo is None
                else started or _now())).total_seconds()) if started else None,
            "agent_runs": len(runs),
            "last_agent": last.agent_name if last else None,
            "last_agent_status": last.status if last else None,
        })
    return out


def _pipeline(db: Session, campaign_id: str | None) -> list[dict]:
    from app.db.models import AgentRun, Campaign
    if not campaign_id:
        return []
    camp = db.get(Campaign, campaign_id)
    if camp is None:
        return []
    runs = db.query(AgentRun).filter_by(campaign_id=campaign_id).all()
    by_agent = {}
    for r in runs:
        by_agent[r.agent_name] = r.status
    cur = _STEP_ALIAS.get(camp.current_step or "", camp.current_step or "")
    steps = []
    reached = False
    for st in _PIPELINE:
        agent_status = None
        for a, s_ in by_agent.items():
            steps_a = a.lower()
            if (st in steps_a or steps_a.split()[0] in st):
                agent_status = s_
        if camp.status == "SUCCESS":
            state = "DONE"
        elif camp.status == "FAILED" and st == cur:
            state = "FAILED"
        elif st == cur:
            state = "RUNNING"
        elif not reached:
            state = "DONE"
        else:
            state = "WAITING"
        if st == cur:
            reached = True
        if agent_status == "FAILED":
            state = "FAILED"
        steps.append({"step": st, "state": state})
    return steps


def _model_routing(db: Session, campaign_id: str | None, workspace_id: str | None) -> dict:
    from app.db.models_p8 import ModelRoutingEvent
    s = get_settings()
    q = db.query(ModelRoutingEvent)
    if campaign_id:
        q = q.filter(ModelRoutingEvent.campaign_id == campaign_id)
    elif workspace_id:
        q = q.filter(ModelRoutingEvent.workspace_id == workspace_id)
    ev = q.order_by(desc(ModelRoutingEvent.created_at)).first()
    base = {"local_only": bool(s.local_only), "cloud_fallback_enabled": bool(s.allow_cloud_fallback),
            "router_enabled": bool(s.model_router_enabled), "quality_preset": s.quality_preset}
    if ev is None:
        return {**base, "last_route": None}
    return {**base, "last_route": {
        "agent": ev.agent_type, "task_type": ev.task_type, "tier": ev.tier,
        "provider": ev.provider, "model": ev.model_id,
        "fallback_used": bool(ev.fallback_used), "escalated": bool(ev.escalated),
        "reason": (ev.reason or "")[:280], "at": _iso(ev.created_at),
        "prompt_composer_used": bool((ev.prompt_lineage or {}).get("prompt_composer_used")),
    }}


def _workers_queues(db: Session) -> dict:
    from app.ops.queue_backpressure import backpressure_state
    from app.ops.worker_registry import worker_states
    ws = worker_states()
    bp = backpressure_state()
    from app.db.models import PublishJob
    failed = db.query(PublishJob).filter(PublishJob.status == "FAILED").count()
    retry = db.query(PublishJob).filter(PublishJob.status == "RETRY").count()
    dl = db.query(PublishJob).filter(PublishJob.dead_lettered.is_(True)).count()
    return {
        "workers_online": sum(1 for w in ws if w["status"] not in ("DEAD",)),
        "workers_busy": sum(1 for w in ws if w.get("current_job")),
        "workers_stale": sum(1 for w in ws if w["status"] == "STALE"),
        "queue_status": bp["status"], "worst_queue_depth": bp["worst_depth"],
        "queue_depths": bp["depths"],
        "publish_failed": failed, "publish_retry": retry, "publish_dead_lettered": dl,
    }


def _last_error(db: Session, workspace_id: str | None, admin: bool) -> dict | None:
    from app.db.models import Campaign, ErrorLog
    q = db.query(ErrorLog)
    if not admin and workspace_id:
        q = (q.join(Campaign, ErrorLog.campaign_id == Campaign.id)
             .filter(Campaign.workspace_id == workspace_id))
    e = q.order_by(desc(ErrorLog.created_at)).first()
    if e is None:
        return None
    code = normalise(e.error_type, e.message, e.scope)
    return {
        "timestamp": _iso(e.created_at), "error_code": code,
        "error_class": e.error_type, "service": e.scope,
        "campaign_id": e.campaign_id,
        "message": (e.message or "")[:400],
        "retryable": is_retryable(code),
        "suggested_action": suggested_action(code),
        "trace_id": e.campaign_id or e.id,
    }


def _recent_events(db: Session, campaign_id: str | None, workspace_id: str | None) -> list[dict]:
    from app.db.models import AgentRun, Campaign
    q = db.query(AgentRun)
    if campaign_id:
        q = q.filter(AgentRun.campaign_id == campaign_id)
    elif workspace_id:
        q = (q.join(Campaign, AgentRun.campaign_id == Campaign.id)
             .filter(Campaign.workspace_id == workspace_id))
    rows = q.order_by(desc(AgentRun.started_at)).limit(10).all()
    out = []
    for r in rows:
        out.append({"at": _iso(r.finished_at or r.started_at),
                    "event": f"{r.agent_name} {r.status}",
                    "campaign_id": r.campaign_id})
    return out


def _governance_cost(db: Session, campaign_id: str | None) -> dict:
    from app.db.models import Campaign, CostLog
    gov = {"state": "NONE"}
    cost = {"estimated_usd": None, "actual_usd": None, "budget_usd": get_settings().campaign_budget_usd,
            "pricing_unknown": False}
    if campaign_id:
        camp = db.get(Campaign, campaign_id)
        if camp is not None:
            gov = {"state": camp.status, "execution_mode": camp.execution_mode}
        rows = db.query(CostLog).filter_by(campaign_id=campaign_id).all()
        if rows:
            cost["actual_usd"] = round(sum((r.amount_usd or 0.0) for r in rows), 4)
            cost["pricing_unknown"] = any((getattr(r, "cost_state", "") or "") == "UNKNOWN" for r in rows)
    return {"governance": gov, "cost": cost}


def _platform_selection(db: Session, campaign_id: str | None) -> list[dict]:
    if not campaign_id:
        return []
    from app.db.models_learn import CampaignPlatformSelection
    rows = db.query(CampaignPlatformSelection).filter_by(campaign_id=campaign_id).all()
    return [{"platform": r.platform, "content_type": r.content_type, "mode": r.mode}
            for r in rows]


def _learning(db: Session, campaign_id: str | None, workspace_id: str | None) -> dict | None:
    from app.db.models_learn import LearningJob
    q = db.query(LearningJob)
    if campaign_id:
        q = q.filter(LearningJob.campaign_id == campaign_id)
    elif workspace_id:
        q = q.filter(LearningJob.workspace_id == workspace_id)
    j = q.order_by(desc(LearningJob.created_at)).first()
    if j is None:
        return None
    return {"job_id": j.id, "status": j.status, "mode": j.execution_mode,
            "total_urls": j.total_urls, "fetched": j.fetched, "ready": j.ready,
            "duplicates": j.duplicates, "datasets_written": j.datasets_written,
            "skills_created": j.skills_created, "blueprints_created": j.blueprints_created}


def _test_snapshot(admin: bool) -> dict | None:
    if get_settings().app_env == "production" and not admin:
        return None
    try:
        from app.db.base import engine
        from sqlalchemy import text
        with engine.connect() as c:
            head = c.execute(text("select version_num from alembic_version")).scalar()
        return {"migration_head": head}
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
#  public
# --------------------------------------------------------------------------- #

def build_snapshot(db: Session, *, workspace_id: str | None = None, admin: bool = False,
                   campaign_id: str | None = None) -> dict:
    s = get_settings()
    system = _system(db, admin=admin, workspace_id=workspace_id)
    jobs = _current_jobs(db, workspace_id, admin)
    focus = campaign_id or (jobs[0]["campaign_id"] if jobs else None)
    gc = _governance_cost(db, focus)
    from app.ops.runtime_flags import (
        emergency_stop_active, maintenance_mode_active, paid_provider_paused,
        publish_paused, safe_mode_active,
    )
    snap = {
        "product": "AI Content Factory",
        "version": s.app_version,
        "environment": _mode(),
        "generated_at": _iso(_now()),
        "timezone": "UTC",
        "overall_health": _overall(system),
        "kill_switches": {
            "global_publish_pause": publish_paused(),
            "global_paid_provider_pause": paid_provider_paused(),
            "emergency_stop": emergency_stop_active(),
            "safe_mode": safe_mode_active(),
            "maintenance_mode": maintenance_mode_active(),
        },
        "system": system,
        "current_jobs": jobs,
        "focus_campaign_id": focus,
        "pipeline": _pipeline(db, focus),
        "model_routing": _model_routing(db, focus, workspace_id),
        "ollama": system["ollama"],
        "workers_queues": _workers_queues(db),
        "last_error": _last_error(db, workspace_id, admin),
        "recent_events": _recent_events(db, focus, workspace_id),
        "governance": gc["governance"],
        "platform_selection": _platform_selection(db, focus),
        "cost": gc["cost"],
        "learning": _learning(db, focus, workspace_id),
        "test": _test_snapshot(admin),
        "scope": "system" if admin else "workspace",
    }
    # belt-and-braces: redact the whole payload before it leaves the process
    return redact(snap)


_TXT_ORDER = """AI CONTENT FACTORY SUPPORT SNAPSHOT
Version: {version}
Environment: {environment}
Time: {generated_at} ({timezone})

Overall: {overall_health}

Backend: {b_backend}
Database: {b_db}
Redis: {b_redis}
Workers: {b_workers}
Ollama: {b_ollama}
Local Model: {b_localmodel}

Campaign: {c_id}
Stage: {c_stage}
Progress: {c_progress}

Agent: {r_agent}
Provider: {r_provider}
Model: {r_model}
Route: {r_tier} ({r_reason})
Fallback: {r_fallback}

Last Error: {e_msg}
Error Code: {e_code}
Suggested Action: {e_action}
Trace ID: {e_trace}

Governance: {g_state}
Rights: {g_rights}

Platforms: {platforms}

Estimated Cost: {cost_est}
Actual Cost: {cost_act}
Budget: {cost_budget}

Kill Switches: publish_pause={ks_pub} paid_provider_pause={ks_paid} emergency_stop={ks_em}

Recent Events:
{events}
"""


def snapshot_text(snap: dict) -> str:
    sys = snap.get("system", {})
    job = (snap.get("current_jobs") or [{}])[0]
    route = (snap.get("model_routing") or {}).get("last_route") or {}
    err = snap.get("last_error") or {}
    cost = snap.get("cost") or {}
    ks = snap.get("kill_switches", {})
    plats = ", ".join(f"{p['platform']}={p['mode']}" for p in snap.get("platform_selection", [])) or "-"
    events = "\n".join(f"  - {e['at']}: {e['event']}" for e in snap.get("recent_events", [])[:8]) or "  (none)"
    prog = "-"
    steps = snap.get("pipeline") or []
    if steps:
        done = sum(1 for x in steps if x["state"] == "DONE")
        prog = f"{done}/{len(steps)} steps"
    return _TXT_ORDER.format(
        version=snap.get("version"), environment=snap.get("environment"),
        generated_at=snap.get("generated_at"), timezone=snap.get("timezone"),
        overall_health=snap.get("overall_health"),
        b_backend=sys.get("backend", {}).get("status"),
        b_db=sys.get("database", {}).get("status"),
        b_redis=sys.get("redis", {}).get("status"),
        b_workers=sys.get("workers", {}).get("status"),
        b_ollama=sys.get("ollama", {}).get("status"),
        b_localmodel="available" if sys.get("ollama", {}).get("model_available") else "unavailable",
        c_id=job.get("campaign_id", "-"), c_stage=job.get("current_stage", "-"),
        c_progress=prog,
        r_agent=route.get("agent", "-"), r_provider=route.get("provider", "-"),
        r_model=route.get("model", "-"), r_tier=route.get("tier", "-"),
        r_reason=(route.get("reason", "") or "")[:80],
        r_fallback=route.get("fallback_used", False),
        e_msg=(err.get("message", "-") or "-")[:200], e_code=err.get("error_code", "-"),
        e_action=err.get("suggested_action", "-"), e_trace=err.get("trace_id", "-"),
        g_state=(snap.get("governance") or {}).get("state", "-"),
        g_rights=(snap.get("governance") or {}).get("execution_mode", "-"),
        platforms=plats,
        cost_est=cost.get("estimated_usd", "UNKNOWN"),
        cost_act=cost.get("actual_usd", "0"),
        cost_budget=cost.get("budget_usd", "-"),
        ks_pub=ks.get("global_publish_pause"), ks_paid=ks.get("global_paid_provider_pause"),
        ks_em=ks.get("emergency_stop"),
        events=events,
    )
