from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.db.models import (
    AutopilotDecision,
    AutopilotRun,
    Campaign,
    PeriodReport,
    RawTrendEvent,
    TopicCandidate,
    TrendSource,
)


def daily_report(session, run_id: str | None = None) -> dict:
    run = (session.get(AutopilotRun, run_id) if run_id
           else session.query(AutopilotRun).order_by(AutopilotRun.started_at.desc()).first())
    if run is None:
        return {"error": "no autopilot run"}
    cands = session.query(TopicCandidate).filter_by(run_id=run.id).all()
    selected = [c for c in cands if c.status in ("SELECTED", "PRODUCING", "SCHEDULED")]
    produced = [c for c in cands if c.campaign_id]
    rejected = [c for c in cands if c.status in ("REJECTED", "BLOCKED", "CANCELLED")]
    sources_checked = list({e.source_id for e in
                            session.query(RawTrendEvent).filter_by(run_id=run.id)})
    return {
        "run_id": run.id, "mode": run.mode, "status": run.status,
        "trend_sources_checked": sources_checked,
        "candidates_found": len(cands),
        "candidates_rejected": len(rejected),
        "selected_topics": [{"topic": c.topic, "angle": c.angle,
                             "opportunity": c.opportunity_score,
                             "portfolio_type": c.portfolio_type,
                             "platforms": list((c.platform_scores or {}).keys())[:4]}
                            for c in selected],
        "produced": len(produced),
        "scheduled": sum(1 for c in cands if c.status == "SCHEDULED"),
        "estimated_cost": run.estimated_cost,
        "actual_cost": run.actual_cost,
        "warnings": run.summary.get("watchdog", []),
        "decisions": [{"type": d.decision_type, "selected": d.selected, "reason": d.reason}
                      for d in session.query(AutopilotDecision).filter_by(run_id=run.id)
                      .order_by(AutopilotDecision.created_at)][:60],
    }


def weekly_autopilot_report(session, period_key: str | None = None) -> PeriodReport:
    period_key = period_key or datetime.now(timezone.utc).strftime("%Y-W%V")
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    runs = session.query(AutopilotRun).filter(AutopilotRun.started_at >= week_ago).all()
    cands = (session.query(TopicCandidate)
             .filter(TopicCandidate.created_at >= week_ago).all())
    produced = [c for c in cands if c.campaign_id]
    cancelled = [c for c in cands if c.status == "CANCELLED"]

    # selection accuracy proxy: produced campaigns that ended SUCCESS
    camp_ids = [c.campaign_id for c in produced]
    succeeded = 0
    if camp_ids:
        succeeded = int(session.query(func.count(Campaign.id))
                        .filter(Campaign.id.in_(camp_ids), Campaign.status == "SUCCESS").scalar() or 0)

    src_value = {t.source_id: t.value_score for t in session.query(TrendSource)}
    best_src = max(src_value, key=src_value.get) if src_value else None
    worst_src = min(src_value, key=src_value.get) if src_value else None

    from app.autopilot.calibration import calibrate

    cal = calibrate(session)

    body = {
        "runs": len(runs),
        "candidates": len(cands),
        "produced": len(produced),
        "cancelled_trends": len(cancelled),
        "selection_success_rate": round(succeeded / len(produced), 3) if produced else None,
        "opportunity_prediction": cal,
        "best_trend_source": best_src,
        "worst_trend_source": worst_src,
        "source_value_scores": src_value,
        "budget_efficiency_note": "actual cost is $0 in mock mode",
    }
    row = session.query(PeriodReport).filter_by(period_type="autopilot_weekly",
                                                period_key=period_key).first()
    if row is None:
        row = PeriodReport(period_type="autopilot_weekly", period_key=period_key)
        session.add(row)
    row.body = body
    session.flush()
    return row
