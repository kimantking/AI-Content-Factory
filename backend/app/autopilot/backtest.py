from __future__ import annotations

from app.autopilot.scoring import score_opportunity
from app.autopilot.signals import natural_content_score, risk_classify
from app.db.models import ContentFeature, PerformanceScore


def backtest(session, *, objective: str = "BALANCED", limit: int = 40) -> dict:
    """Replay: treat our own past content as 'candidates', score them with the
    CURRENT opportunity formula, and see which the engine would have picked.

    This is a diagnostic of the scorer, NOT a prediction of future results.
    """
    feats = {f.content_id: f for f in session.query(ContentFeature).all()}
    rows = []
    for ps in session.query(PerformanceScore).order_by(PerformanceScore.computed_at.desc()).limit(limit):
        cf = feats.get(ps.content_id)
        if cf is None:
            continue
        risk_level, risk_cats, risk_sc = risk_classify(cf.topic or "", {})
        dims = {
            "trend": 55.0, "velocity": 55.0, "acceleration": 50.0, "freshness": 50.0,
            "historical": min(100.0, ps.score),
            "audience_fit": min(100.0, (ps.relative_score or 1.0) * 55.0),
            "revenue": 45.0, "profit": 50.0, "competition": 55.0, "saturation": 50.0,
            "originality": 55.0, "fact_availability": 65.0, "production_cost": 65.0,
            "difficulty": 40.0,
            "natural_content": natural_content_score(cf.topic or "", {}),
            "fatigue": 20.0, "risk": risk_sc,
        }
        res = score_opportunity(dims, objective=objective)
        rows.append({
            "content_id": cf.content_id, "topic": cf.topic,
            "predicted_opportunity": res["opportunity_score"],
            "actual_score": ps.score, "actual_relative": ps.relative_score,
            "would_select": res["opportunity_score"] >= 55.0,
        })
    rows.sort(key=lambda r: r["predicted_opportunity"], reverse=True)
    picked = [r for r in rows if r["would_select"]]
    # crude rank correlation sign
    hits = sum(1 for r in picked if (r["actual_relative"] or 0) >= 1.0)
    return {
        "objective": objective, "evaluated": len(rows), "would_select": len(picked),
        "selected_that_actually_outperformed": hits,
        "note": "diagnostic of the scoring formula on historical data — not a performance guarantee",
        "rows": rows[:20],
    }
