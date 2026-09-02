from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics.capabilities import load_analytics_capabilities
from app.analytics.revenue import cost_breakdown, profit_report, revenue_breakdown
from app.config import get_settings
from app.db.base import get_db
from app.db.models import (
    AnalyticsSnapshot,
    Campaign,
    ContentFeature,
    ContentRecipe,
    Experiment,
    LearningMemory,
    LearningRun,
    PerformanceScore,
    PeriodReport,
    Publication,
)

router = APIRouter(prefix="/api", tags=["analytics"])

_METRIC_COLS = ["views", "impressions", "reach", "watch_time_seconds",
                "avg_view_percentage", "likes", "comments", "shares", "saves",
                "followers_gained", "subscribers_gained", "estimated_revenue"]


@router.get("/analytics/capabilities")
def analytics_capabilities():
    return [c.__dict__ for c in load_analytics_capabilities().values()]


@router.get("/analytics/overview")
def analytics_overview(db: Session = Depends(get_db)):
    out: dict = {"metrics": {}, "note": "— = UNAVAILABLE for the connected platforms"}
    for col in _METRIC_COLS:
        agg = "max" if col in ("views", "impressions", "reach") else "sum"
        fn = func.max if agg == "max" else func.sum
        rows = db.query(fn(getattr(AnalyticsSnapshot, col))).filter(
            getattr(AnalyticsSnapshot, col).isnot(None)).scalar()
        out["metrics"][col] = round(float(rows), 2) if rows is not None else None
    # availability rollup across snapshots
    avail: dict[str, set] = {}
    for s in db.query(AnalyticsSnapshot.metric_availability).limit(500):
        for k, v in (s[0] or {}).items():
            avail.setdefault(k, set()).add(v)
    out["availability"] = {k: sorted(v) for k, v in avail.items()}
    p = profit_report_all(db)
    out["revenue"] = p["revenue"]
    out["cost"] = p["cost"]
    out["net_profit"] = p["net_profit"]
    out["margin"] = p["margin"]
    return out


def profit_report_all(db: Session) -> dict:
    net = rev = cost = 0.0
    for (cid,) in db.query(Campaign.id).all():
        p = profit_report(db, cid)
        net += p["net_profit"]
        rev += p["revenue"]["total"]
        cost += p["cost"]["total"]
    return {"revenue": {"total": round(rev, 4)}, "cost": {"total": round(cost, 6)},
            "net_profit": round(net, 4), "margin": round(net / rev, 4) if rev else None}


@router.get("/analytics/platforms/{platform}")
def analytics_by_platform(platform: str, db: Session = Depends(get_db)):
    snaps = (db.query(AnalyticsSnapshot).filter_by(platform=platform)
             .order_by(AnalyticsSnapshot.collected_at.desc()).limit(200).all())
    return {
        "platform": platform,
        "snapshot_count": len(snaps),
        "latest": [{"publication_id": s.publication_id, "window": s.window_label,
                    "views": s.views, "watch_time_seconds": s.watch_time_seconds,
                    "avg_view_percentage": s.avg_view_percentage, "likes": s.likes,
                    "shares": s.shares, "status": s.collection_status,
                    "availability": s.metric_availability, "anomaly": s.anomaly_flags}
                   for s in snaps[:50]],
    }


@router.get("/analytics/rankings")
def content_rankings(sort: str = "score", db: Session = Depends(get_db), limit: int = 30):
    order_map = {
        "score": PerformanceScore.score.desc(),
        "relative": PerformanceScore.relative_score.desc(),
    }
    if sort in order_map:
        rows = db.query(PerformanceScore).order_by(order_map[sort]).limit(limit).all()
        return [{"content_id": r.content_id, "platform": r.platform, "score": r.score,
                 "relative_score": r.relative_score, "objective": r.objective,
                 "is_outlier": r.is_outlier, "has_anomaly": r.has_anomaly,
                 "components": r.components} for r in rows]
    col = getattr(AnalyticsSnapshot, sort, None)
    if col is None:
        raise HTTPException(400, f"unknown sort '{sort}'")
    rows = (db.query(AnalyticsSnapshot).filter(col.isnot(None))
            .order_by(col.desc()).limit(limit).all())
    return [{"content_id": s.content_id, "platform": s.platform, sort: getattr(s, sort),
             "window": s.window_label} for s in rows]


@router.get("/campaigns/{campaign_id}/analytics")
def campaign_analytics(campaign_id: str, db: Session = Depends(get_db)):
    snaps = db.query(AnalyticsSnapshot).filter_by(campaign_id=campaign_id).all()
    scores = db.query(PerformanceScore).filter_by(campaign_id=campaign_id).all()
    return {
        "campaign_id": campaign_id,
        "snapshots": [{"publication_id": s.publication_id, "platform": s.platform,
                       "window": s.window_label, "views": s.views,
                       "status": s.collection_status, "availability": s.metric_availability}
                      for s in snaps],
        "performance": [{"content_id": p.content_id, "platform": p.platform,
                         "score": p.score, "relative_score": p.relative_score,
                         "objective": p.objective, "outlier": p.is_outlier} for p in scores],
        "profit": profit_report(db, campaign_id),
    }


@router.get("/analytics/naturalness")
def naturalness_analytics(db: Session = Depends(get_db)):
    feats = {f.content_id: f for f in db.query(ContentFeature).all()}
    rows = []
    for ps in db.query(PerformanceScore).all():
        cf = feats.get(ps.content_id)
        if cf is None:
            continue
        rows.append({"content_id": ps.content_id, "platform": ps.platform,
                     "ai_slop_score": cf.ai_slop_score, "ai_video_ratio": cf.ai_video_ratio,
                     "stock_ratio": cf.stock_ratio,
                     "scene_duration_variance": cf.scene_duration_variance,
                     "subtitle_highlight_frequency": cf.subtitle_highlight_frequency,
                     "performance_score": ps.score})
    return {"n": len(rows), "rows": rows,
            "note": "correlation only — not causal"}


@router.get("/analytics/revenue")
def revenue_dashboard(campaign_id: str | None = None, db: Session = Depends(get_db)):
    if campaign_id:
        return profit_report(db, campaign_id)
    agg = profit_report_all(db)
    # add per-source / per-kind breakdown across all campaigns
    src = {"by_source": {}, "actual": 0.0, "estimate": 0.0, "total": 0.0}
    kinds = {"by_kind": {}, "total": 0.0}
    for (cid,) in db.query(Campaign.id).all():
        r = revenue_breakdown(db, cid)
        c = cost_breakdown(db, cid)
        for k, v in r["by_source"].items():
            src["by_source"][k] = src["by_source"].get(k, 0.0) + v
        src["actual"] += r["actual"]
        src["estimate"] += r["estimate"]
        src["total"] += r["total"]
        for k, v in c["by_kind"].items():
            kinds["by_kind"][k] = kinds["by_kind"].get(k, 0.0) + v
        kinds["total"] += c["total"]
    agg["revenue_detail"] = src
    agg["cost_detail"] = kinds
    return agg


# ---- learning ----------------------------------------------------------- #

@router.get("/learning/dashboard")
def learning_dashboard(db: Session = Depends(get_db)):
    mems = db.query(LearningMemory).order_by(LearningMemory.confidence.desc()).all()
    def pack(m):
        return {"id": m.id, "type": m.memory_type, "platform": m.platform,
                "dimension": m.dimension, "statement": m.statement, "status": m.status,
                "confidence": m.confidence, "sample_size": m.sample_size,
                "recommendation": m.recommendation, "evidence_ids": (m.evidence_ids or [])[:5]}
    return {
        "strong": [pack(m) for m in mems if m.status == "STRONG"],
        "moderate": [pack(m) for m in mems if m.status == "MODERATE"],
        "experimental": [pack(m) for m in mems if m.status in ("EXPERIMENTAL", "WEAK")],
        "last_run": (lambda r: {"run_date": r.run_date, "summary": r.summary} if r else None)(
            db.query(LearningRun).order_by(LearningRun.run_date.desc()).first()),
    }


@router.get("/learning/memories")
def list_memories(memory_type: str | None = None, platform: str | None = None,
                  status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(LearningMemory)
    if memory_type:
        q = q.filter_by(memory_type=memory_type)
    if platform:
        q = q.filter_by(platform=platform)
    if status:
        q = q.filter_by(status=status)
    return [{"id": m.id, "type": m.memory_type, "platform": m.platform,
             "content_type": m.content_type, "topic_cluster": m.topic_cluster,
             "dimension": m.dimension, "statement": m.statement, "status": m.status,
             "confidence": m.confidence, "sample_size": m.sample_size,
             "pinned": m.pinned, "hard_policy": m.hard_policy,
             "evidence_ids": m.evidence_ids} for m in q.order_by(LearningMemory.confidence.desc())]


@router.post("/learning/memories/{memory_id}/{action}")
def memory_action(memory_id: str, action: str, db: Session = Depends(get_db)):
    m = db.get(LearningMemory, memory_id)
    if m is None:
        raise HTTPException(404, "memory not found")
    if m.hard_policy and action in ("disable", "delete"):
        raise HTTPException(403, "hard policy memory cannot be modified here")
    if action == "pin":
        m.pinned = True
    elif action == "unpin":
        m.pinned = False
    elif action == "disable":
        m.status = "DEPRECATED"
    elif action == "delete":
        db.delete(m)
    else:
        raise HTTPException(400, f"unknown action '{action}'")
    db.commit()
    return {"ok": True, "action": action}


@router.get("/learning/recipes")
def list_recipes(db: Session = Depends(get_db)):
    return [{"id": r.id, "platform": r.platform, "content_type": r.content_type,
             "topic_cluster": r.topic_cluster, "objective": r.objective, "recipe": r.recipe,
             "confidence": r.confidence, "sample_size": r.sample_size, "status": r.status}
            for r in db.query(ContentRecipe).order_by(ContentRecipe.confidence.desc())]


@router.get("/learning/experiments")
def list_experiments(db: Session = Depends(get_db)):
    return [{"id": e.id, "hypothesis": e.hypothesis, "variable": e.variable,
             "platform": e.platform, "design": e.design, "status": e.status,
             "result": e.result, "confidence": e.confidence} for e in db.query(Experiment)]


@router.post("/learning/run")
def run_learning(db: Session = Depends(get_db)):
    from app.learning.reports import daily_learning_run

    run = daily_learning_run(db)
    db.commit()
    return {"run_date": run.run_date, "summary": run.summary,
            "memories_touched": run.memories_touched, "recipes_touched": run.recipes_touched}


@router.get("/reports/{period_type}")
def get_report(period_type: str, key: str | None = None, db: Session = Depends(get_db)):
    if period_type not in ("weekly", "monthly"):
        raise HTTPException(400, "period_type must be weekly|monthly")
    if key is None:
        from app.learning.reports import monthly_report, weekly_report

        row = weekly_report(db) if period_type == "weekly" else monthly_report(db)
        db.commit()
    else:
        row = db.query(PeriodReport).filter_by(period_type=period_type, period_key=key).first()
        if row is None:
            raise HTTPException(404, "report not found")
    return {"period_type": row.period_type, "period_key": row.period_key, "body": row.body}


@router.get("/analytics/opportunity-inputs")
def opportunity_inputs_endpoint(platform: str | None = None, db: Session = Depends(get_db)):
    from app.learning.opportunity import opportunity_inputs

    return opportunity_inputs(db, platform=platform)


@router.post("/analytics/collect/{publication_id}")
def manual_collect(publication_id: str, window: str = Body("adhoc", embed=True),
                   db: Session = Depends(get_db)):
    from app.analytics.performance import compute_performance_score
    from app.analytics.snapshot import collect_snapshot

    if db.get(Publication, publication_id) is None:
        raise HTTPException(404, "publication not found")
    snap = collect_snapshot(db, publication_id, window)
    ps = compute_performance_score(db, publication_id, get_settings().default_objective)
    db.commit()
    return {"snapshot_id": snap.id, "collection_status": snap.collection_status,
            "availability": snap.metric_availability, "performance_score": ps.score}
