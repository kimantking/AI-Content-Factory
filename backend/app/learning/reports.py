from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import func

from app.analytics.revenue import profit_report
from app.db.models import (
    AnalyticsSnapshot,
    Campaign,
    ContentFeature,
    Experiment,
    LearningMemory,
    LearningRun,
    PerformanceScore,
    PeriodReport,
)
from app.learning.engine import analyze
from app.learning.recipe import build_recipes
from app.learning.experiment import evaluate_all


def daily_learning_run(session, run_date: str | None = None) -> LearningRun:
    """Idempotent by run_date — a re-run (crash recovery) updates the same row."""
    run_date = run_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = session.query(LearningRun).filter_by(run_date=run_date).first()

    snap_n = session.query(func.count(AnalyticsSnapshot.id)).scalar() or 0
    summary = analyze(session)
    recipes = build_recipes(session)
    completed = evaluate_all(session)
    mem_n = session.query(func.count(LearningMemory.id)).scalar() or 0

    row = existing or LearningRun(run_date=run_date)
    row.snapshots_analyzed = int(snap_n)
    row.memories_touched = int(mem_n)
    row.recipes_touched = int(recipes)
    row.summary = {**summary, "experiments_completed": completed}
    row.status = "SUCCESS"
    if existing is None:
        session.add(row)
    session.flush()
    return row


def _best_by(session, dim_attr: str, objective: str = "BALANCED") -> dict:
    feats = {f.content_id: f for f in session.query(ContentFeature).all()}
    buckets: dict[str, list[float]] = defaultdict(list)
    for ps in session.query(PerformanceScore).filter_by(objective=objective).all():
        cf = feats.get(ps.content_id)
        if cf is None:
            continue
        v = getattr(cf, dim_attr, None)
        if v is not None:
            buckets[str(v)].append(ps.score)
    ranked = sorted(((k, statistics.median(v), len(v)) for k, v in buckets.items() if len(v) >= 2),
                    key=lambda x: x[1], reverse=True)
    return {"best": ranked[0][0] if ranked else None,
            "ranking": [{"value": k, "median_score": round(m, 1), "n": n} for k, m, n in ranked]}


def weekly_report(session, period_key: str | None = None) -> PeriodReport:
    period_key = period_key or datetime.now(timezone.utc).strftime("%Y-W%V")
    body = {
        "best_topics": _best_by(session, "topic_cluster"),
        "best_hooks": _best_by(session, "hook_type"),
        "best_cta": _best_by(session, "cta_type"),
        "best_duration": _best_by(session, "video_duration"),
        "best_subtitle": _best_by(session, "subtitle_style"),
        "naturalness_patterns": _best_by(session, "ai_slop_score"),
        "experiments": [{"id": e.id, "variable": e.variable, "status": e.status,
                         "result": e.result} for e in session.query(Experiment).all()],
        "strong_memories": [m.statement for m in session.query(LearningMemory)
                            .filter_by(status="STRONG").limit(20)],
        "recommendations": _recommendations(session),
    }
    row = _upsert_period(session, "weekly", period_key, body)
    return row


def monthly_report(session, period_key: str | None = None) -> PeriodReport:
    period_key = period_key or datetime.now(timezone.utc).strftime("%Y-%m")
    total_views = int(session.query(func.coalesce(func.sum(AnalyticsSnapshot.views), 0))
                      .scalar() or 0)
    campaigns = session.query(Campaign).count()
    # aggregate profit across campaigns that have any revenue/cost
    camp_ids = [c[0] for c in session.query(Campaign.id).all()]
    agg_net = agg_rev = agg_cost = 0.0
    for cid in camp_ids:
        p = profit_report(session, cid)
        agg_net += p["net_profit"]
        agg_rev += p["revenue"]["total"]
        agg_cost += p["cost"]["total"]
    body = {
        "total_views_ref": total_views, "campaigns": campaigns,
        "revenue_total": round(agg_rev, 4), "cost_total": round(agg_cost, 6),
        "net_profit": round(agg_net, 4),
        "margin": round(agg_net / agg_rev, 4) if agg_rev else None,
        "best_platform": _best_platform(session),
        "best_content": _best_content(session),
        "recommendations": _recommendations(session),
    }
    return _upsert_period(session, "monthly", period_key, body)


def _best_platform(session) -> dict:
    rows = (session.query(PerformanceScore.platform, func.avg(PerformanceScore.score))
            .group_by(PerformanceScore.platform).all())
    ranked = sorted(((p, float(s)) for p, s in rows), key=lambda x: x[1], reverse=True)
    return {"best": ranked[0][0] if ranked else None,
            "ranking": [{"platform": p, "avg_score": round(s, 1)} for p, s in ranked]}


def _best_content(session) -> list[dict]:
    rows = (session.query(PerformanceScore)
            .order_by(PerformanceScore.score.desc()).limit(5).all())
    return [{"content_id": r.content_id, "platform": r.platform, "score": r.score,
             "outlier": r.is_outlier} for r in rows]


def _recommendations(session) -> list[dict]:
    out = []
    for m in (session.query(LearningMemory)
              .filter(LearningMemory.status.in_(["MODERATE", "STRONG"]))
              .order_by(LearningMemory.confidence.desc()).limit(10)):
        out.append({"statement": m.statement, "recommendation": m.recommendation,
                    "confidence": m.confidence, "sample_size": m.sample_size,
                    "evidence_ids": m.evidence_ids[:5], "status": m.status})
    return out


def _upsert_period(session, ptype: str, key: str, body: dict) -> PeriodReport:
    existing = session.query(PeriodReport).filter_by(period_type=ptype, period_key=key).first()
    row = existing or PeriodReport(period_type=ptype, period_key=key)
    row.body = body
    if existing is None:
        session.add(row)
    session.flush()
    return row
