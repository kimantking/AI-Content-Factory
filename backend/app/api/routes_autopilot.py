from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.autopilot.config import AUTOPILOT_MODES, apply_config, snapshot_config
from app.autopilot.config import HardRuleViolation
from app.config import get_settings
from app.db.base import get_db
from app.db.models import (
    AutopilotDecision,
    AutopilotRun,
    CostLog,
    RawTrendEvent,
    TopicCandidate,
    TopicRejection,
    TrendSource,
)
from app.trends.capabilities import load_trend_capabilities

router = APIRouter(prefix="/api/autopilot", tags=["autopilot"])


class ConfigPatch(BaseModel):
    changes: dict
    actor: str = "user"


class RejectRequest(BaseModel):
    scope: str = "ONCE"     # ONCE | PERMANENT
    reason: str = "OTHER"


@router.get("/config")
def get_config():
    return snapshot_config()


@router.post("/config")
def set_config(payload: ConfigPatch, db: Session = Depends(get_db)):
    try:
        version = apply_config(db, payload.changes, actor=payload.actor)
    except HardRuleViolation as e:
        raise HTTPException(403, str(e)) from e
    db.commit()
    return {"config_version": version, "config": snapshot_config()}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    s = get_settings()
    run = db.query(AutopilotRun).order_by(AutopilotRun.started_at.desc()).first()
    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    spent = float(db.query(func.coalesce(func.sum(CostLog.amount_usd), 0.0))
                  .filter(CostLog.created_at >= day_ago).scalar() or 0.0)
    cands = db.query(TopicCandidate).filter_by(run_id=run.id).all() if run else []
    strong = [c for c in cands if (c.opportunity_score or 0) >= s.autopilot_min_opportunity_score]
    return {
        "mode": s.autopilot_mode,
        "emergency_stop": s.autopilot_emergency_stop,
        "today_budget": {"spent": round(spent, 4), "daily": s.autopilot_daily_budget_usd,
                         "hard": s.autopilot_daily_hard_budget_usd,
                         "trend_reserve": round(s.autopilot_daily_budget_usd * s.autopilot_trend_reserve_ratio, 4)},
        "last_run": None if run is None else {
            "run_id": run.id, "mode": run.mode, "status": run.status, "stage": run.stage,
            "started_at": run.started_at.isoformat(), "pause_reason": run.pause_reason,
        },
        "candidates": len(cands),
        "strong_opportunities": len(strong),
        "selected": sum(1 for c in cands if c.status in ("SELECTED", "PRODUCING", "SCHEDULED")),
        "producing": sum(1 for c in cands if c.status == "PRODUCING"),
        "scheduled": sum(1 for c in cands if c.status == "SCHEDULED"),
    }


@router.post("/scan")
def scan(mode: str | None = Body(None, embed=True), db: Session = Depends(get_db)):
    s = get_settings()
    m = (mode or s.autopilot_mode).upper()
    if m not in AUTOPILOT_MODES:
        raise HTTPException(400, f"mode must be one of {AUTOPILOT_MODES}")
    from app.celery_app import celery_app  # noqa: F401
    from app.tasks import autopilot_run_task

    if s.run_inline:
        return autopilot_run_task.apply(args=[m, "manual"]).get()
    try:
        autopilot_run_task.apply_async(args=[m, "manual"], queue="autopilot")
        return {"state": "queued", "mode": m}
    except Exception:
        return autopilot_run_task.apply(args=[m, "manual"]).get()


@router.post("/pause")
def pause(run_id: str = Body(..., embed=True), reason: str = Body("manual pause", embed=True),
          db: Session = Depends(get_db)):
    from app.autopilot.emergency import pause_run

    r = pause_run(db, run_id, reason)
    db.commit()
    return r


@router.post("/resume")
def resume(run_id: str = Body(..., embed=True), db: Session = Depends(get_db)):
    from app.autopilot.emergency import resume_run

    r = resume_run(db, run_id)
    db.commit()
    return r


@router.post("/emergency-stop")
def emergency_stop(db: Session = Depends(get_db)):
    from app.autopilot.emergency import emergency_stop as _stop

    r = _stop(db, actor="user")
    db.commit()
    return r


@router.post("/resume-stop")
def resume_stop(db: Session = Depends(get_db)):
    from app.autopilot.emergency import resume_after_stop

    r = resume_after_stop(db, actor="user")
    db.commit()
    return r


@router.get("/runs")
def list_runs(db: Session = Depends(get_db), limit: int = 20):
    rows = db.query(AutopilotRun).order_by(AutopilotRun.started_at.desc()).limit(limit).all()
    return [{"run_id": r.id, "mode": r.mode, "trigger": r.trigger, "status": r.status,
             "stage": r.stage, "raw_candidates": r.raw_candidates,
             "final_candidates": r.final_candidates, "selected_count": r.selected_count,
             "estimated_cost": r.estimated_cost, "started_at": r.started_at.isoformat(),
             "pause_reason": r.pause_reason} for r in rows]


@router.get("/runs/{run_id}")
def run_detail(run_id: str, db: Session = Depends(get_db)):
    r = db.get(AutopilotRun, run_id)
    if r is None:
        raise HTTPException(404, "run not found")
    decisions = (db.query(AutopilotDecision).filter_by(run_id=run_id)
                 .order_by(AutopilotDecision.created_at).all())
    return {
        "run_id": r.id, "mode": r.mode, "status": r.status, "stage": r.stage,
        "summary": r.summary, "config_version": r.config_version,
        "decisions": [{"type": d.decision_type, "candidate_id": d.candidate_id,
                       "selected": d.selected, "reason": d.reason} for d in decisions],
    }


@router.get("/candidates")
def candidates(run_id: str | None = None, db: Session = Depends(get_db)):
    if run_id is None:
        r = db.query(AutopilotRun).order_by(AutopilotRun.started_at.desc()).first()
        run_id = r.id if r else None
    if not run_id:
        return []
    rows = (db.query(TopicCandidate).filter_by(run_id=run_id)
            .order_by(TopicCandidate.opportunity_score.desc().nullslast()).all())
    return [_cand_dict(c) for c in rows]


@router.get("/candidates/{candidate_id}/why")
def why_this_topic(candidate_id: str, db: Session = Depends(get_db)):
    c = db.get(TopicCandidate, candidate_id)
    if c is None:
        raise HTTPException(404, "candidate not found")
    score = (c.explanation or {}).get("score", {})
    return {
        "topic": c.topic, "angle": c.angle, "opportunity_score": c.opportunity_score,
        "formula_version": c.opportunity_formula_version,
        "components": score.get("components", {}),
        "all_dimensions": score.get("all_dimensions", {}),
        "dedup_penalty": score.get("dedup_penalty"),
        "reasons": score.get("reasons", []),
        "risk_level": c.risk_level, "risk_categories": c.risk_categories,
        "platform_scores": c.platform_scores,
        "trend_type": c.trend_type, "dedup_status": c.dedup_status,
        "estimated_cost": c.estimated_cost, "confidence": c.confidence,
        "revenue_is_estimate": (c.explanation or {}).get("revenue_is_estimate"),
    }


@router.post("/candidates/{candidate_id}/reject")
def reject(candidate_id: str, payload: RejectRequest, db: Session = Depends(get_db)):
    c = db.get(TopicCandidate, candidate_id)
    if c is None:
        raise HTTPException(404, "candidate not found")
    c.status = "REJECTED"
    db.add(TopicRejection(topic_cluster_id=c.topic_cluster_id, topic=c.topic,
                          scope="PERMANENT" if payload.scope.upper() == "PERMANENT" else "ONCE",
                          reason=payload.reason))
    db.commit()
    return {"ok": True, "scope": payload.scope}


@router.get("/trend-sources")
def trend_sources(db: Session = Depends(get_db)):
    caps = load_trend_capabilities()
    rows = {t.source_id: t for t in db.query(TrendSource).all()}
    out = []
    for sid, cap in caps.items():
        t = rows.get(sid)
        out.append({
            "source_id": sid, "name": cap.name, "source_type": cap.source_type,
            "auth_status": cap.auth_status, "reliability": cap.reliability,
            "known_limitations": cap.known_limitations,
            "health": t.health if t else "UNKNOWN",
            "value_score": t.value_score if t else cap.reliability,
            "last_success": t.last_success.isoformat() if t and t.last_success else None,
        })
    return out


@router.get("/report/daily")
def daily_report(run_id: str | None = None, db: Session = Depends(get_db)):
    from app.autopilot.reports import daily_report as _daily

    return _daily(db, run_id)


@router.get("/report/weekly")
def weekly_report(db: Session = Depends(get_db)):
    from app.autopilot.reports import weekly_autopilot_report

    row = weekly_autopilot_report(db)
    db.commit()
    return {"period_key": row.period_key, "body": row.body}


@router.post("/backtest")
def backtest(objective: str = Body("BALANCED", embed=True), db: Session = Depends(get_db)):
    from app.autopilot.backtest import backtest as _bt

    return _bt(db, objective=objective)


@router.get("/health")
def autopilot_health():
    from app.autopilot.health import provider_health, run_allowed

    h = provider_health()
    ok, down = run_allowed(h)
    return {"health": h, "run_allowed": ok, "down": down}


def _cand_dict(c: TopicCandidate) -> dict:
    return {
        "id": c.id, "topic": c.topic, "angle": c.angle,
        "topic_cluster_id": c.topic_cluster_id, "trend_type": c.trend_type,
        "dedup_status": c.dedup_status, "status": c.status,
        "portfolio_type": c.portfolio_type,
        "opportunity_score": c.opportunity_score,
        "trend_score": c.trend_score, "velocity_score": c.velocity_score,
        "historical_score": c.historical_score, "audience_fit_score": c.audience_fit_score,
        "revenue_score": c.revenue_score, "profit_score": c.profit_score,
        "competition_score": c.competition_score, "originality_score": c.originality_score,
        "fact_availability_score": c.fact_availability_score,
        "natural_content_score": c.natural_content_score,
        "risk_level": c.risk_level, "risk_score": c.risk_score,
        "estimated_cost": c.estimated_cost, "confidence": c.confidence,
        "platform_scores": c.platform_scores, "campaign_id": c.campaign_id,
    }
