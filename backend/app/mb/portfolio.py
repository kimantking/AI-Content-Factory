"""Portfolio Manager (§19-§25, §51, §52, §92-§98, §100) — deterministic.

Scores every channel in a workspace, allocates budget by objective, and emits
*recommendations only* (never auto-deletes a channel, never exceeds a hard
budget, always attaches evidence + sample_size + confidence). A single lucky
outlier can't 5× a channel's budget (§93).
"""
from __future__ import annotations

import statistics

from sqlalchemy.orm import Session

from app.db.models_mb import (
    Channel,
    ChannelHealthSnapshot,
    PortfolioDecision,
    PortfolioSnapshot,
    Workspace,
)
from app.mb import channel_manager as _cm

_OBJ_WEIGHTS = {
    "GROWTH": {"growth": .40, "opportunity": .20, "audience": .15, "efficiency": .10,
               "stability": .10, "risk": .05},
    "REVENUE": {"revenue": .45, "growth": .15, "efficiency": .15, "stability": .15, "risk": .10},
    "PROFIT": {"profit": .45, "efficiency": .25, "revenue": .12, "stability": .12, "risk": .06},
    "DIVERSIFICATION": {"stability": .30, "opportunity": .25, "growth": .20, "risk": .15, "profit": .10},
    "BRAND": {"stability": .30, "audience": .25, "risk": .20, "growth": .15, "opportunity": .10},
    "BALANCED": {"growth": .20, "revenue": .18, "profit": .18, "efficiency": .14,
                 "stability": .14, "opportunity": .10, "risk": .06},
}


def _channel_scores(db: Session, ch: Channel, snap: ChannelHealthSnapshot) -> dict:
    c = snap.components
    return {
        "growth_score": round(0.5 * c.get("audience_growth", 0) + 0.5 * c.get("activity", 0), 1),
        "revenue_score": c.get("revenue", 0.0),
        "profit_score": c.get("profit", 0.0),
        "efficiency_score": c.get("cost_efficiency", 0.0),
        "stability_score": round(0.6 * c.get("publishing_reliability", 0) + 0.4 * c.get("policy_health", 0), 1),
        "audience_score": c.get("audience_growth", 0.0),
        "opportunity_score": round(0.5 * c.get("content_performance", 0) + 0.5 * c.get("topic_diversity", 0), 1),
        "risk_score": round(100.0 - 0.5 * (c.get("policy_health", 100) + c.get("account_health", 100)) / 1.0 / 2 * 2, 1),
        "health_score": snap.score,
        "sample_size": snap.sample_size,
        "scale_status": snap.scale_status,
    }


def _portfolio_score(scores: dict, objective: str) -> float:
    w = _OBJ_WEIGHTS.get(objective.upper(), _OBJ_WEIGHTS["BALANCED"])
    m = {
        "growth": scores["growth_score"], "revenue": scores["revenue_score"],
        "profit": scores["profit_score"], "efficiency": scores["efficiency_score"],
        "stability": scores["stability_score"], "audience": scores["audience_score"],
        "opportunity": scores["opportunity_score"],
        "risk": max(0.0, 100.0 - scores["risk_score"]),   # lower risk is better
    }
    tw = sum(w.values()) or 1.0
    return round(sum(w.get(k, 0.0) * m.get(k, 0.0) for k in w) / tw, 2)


def snapshot(db: Session, workspace_id: str, *, objective: str | None = None) -> PortfolioSnapshot:
    ws = db.get(Workspace, workspace_id)
    objective = (objective or (ws.objective if ws else "BALANCED")).upper()
    channels = db.query(Channel).filter_by(workspace_id=workspace_id).all()
    ch_scores: dict[str, dict] = {}
    for ch in channels:
        snap = (db.query(ChannelHealthSnapshot)
                .filter_by(channel_id=ch.id).order_by(ChannelHealthSnapshot.created_at.desc()).first())
        if snap is None:
            snap = _cm.health_score(db, ch)
        s = _channel_scores(db, ch, snap)
        # score primarily by the WORKSPACE objective (§21, §112) so the portfolio
        # view/allocation shifts with the workspace goal; the channel's own
        # objective is a secondary lens kept for the channel dashboard.
        s["portfolio_score"] = _portfolio_score(s, objective)
        s["portfolio_score_channel_objective"] = _portfolio_score(s, ch.primary_objective or objective)
        s["name"] = ch.name
        s["platform"] = ch.platform
        s["status"] = ch.status
        s["daily_budget_usd"] = ch.daily_budget_usd
        ch_scores[ch.id] = s

    totals = {
        "channels": len(channels),
        "active": sum(1 for ch in channels if ch.status == "ACTIVE"),
        "sum_daily_budget_usd": round(sum(ch.daily_budget_usd for ch in channels), 2),
        "workspace_hard_daily_usd": float(ws.daily_hard_budget_usd) if ws else 0.0,
        "avg_health": round(statistics.fmean([s["health_score"] for s in ch_scores.values()]), 1)
        if ch_scores else 0.0,
    }
    row = PortfolioSnapshot(workspace_id=workspace_id, objective=objective,
                            channels=ch_scores, totals=totals)
    db.add(row)
    db.flush()
    return row


def allocate_budget(db: Session, workspace_id: str, *, objective: str | None = None,
                    total_usd: float | None = None, trend_reserve_frac: float = 0.1,
                    min_exploration_frac: float = 0.05) -> dict:
    """Data-informed recommended split. Sums to <= total and never exceeds the
    workspace daily hard budget. Fairness floor keeps every ACTIVE channel funded
    so experiment channels can still accrue data (§98)."""
    ws = db.get(Workspace, workspace_id)
    objective = (objective or (ws.objective if ws else "BALANCED")).upper()
    hard = float(ws.daily_hard_budget_usd) if ws and ws.daily_hard_budget_usd > 0 else None
    total = total_usd if total_usd is not None else (hard or 0.0)
    if total <= 0:
        return {"objective": objective, "total_usd": 0.0, "allocations": {}, "note": "no budget set"}
    if hard is not None:
        total = min(total, hard)

    snap = snapshot(db, workspace_id, objective=objective)
    active = {cid: s for cid, s in snap.channels.items() if s["status"] == "ACTIVE"}
    if not active:
        return {"objective": objective, "total_usd": round(total, 2), "allocations": {},
                "trend_reserve_usd": round(total * trend_reserve_frac, 2)}

    trend_reserve = total * trend_reserve_frac
    distributable = total - trend_reserve
    floor = (distributable * min_exploration_frac) / len(active)

    weights = {cid: max(1.0, s["portfolio_score"]) for cid, s in active.items()}
    # dampen: warmup / low-sample channels get a flat weight (no confident scaling — §113/§114)
    for cid, s in active.items():
        if s["sample_size"] < 12 or s["scale_status"] in ("NOT_ENOUGH_DATA", "TEST_MORE"):
            weights[cid] = min(weights[cid], 40.0)
    wsum = sum(weights.values()) or 1.0
    allocations: dict[str, float] = {}
    for cid in active:
        share = (distributable - floor * len(active)) * (weights[cid] / wsum) + floor
        allocations[cid] = round(max(0.0, share), 2)

    return {
        "objective": objective, "total_usd": round(total, 2),
        "trend_reserve_usd": round(trend_reserve, 2),
        "min_exploration_floor_usd": round(floor, 2),
        "allocations": allocations,
        "hard_capped": hard is not None and (total_usd or 0) > hard,
    }


def recommendations(db: Session, workspace_id: str) -> list[PortfolioDecision]:
    """CONTINUE / INCREASE_BUDGET / REDUCE_PRODUCTION / EXPERIMENT / PAUSE_RECOMMENDED /
    REPOSITION_RECOMMENDED / REVIEW_REQUIRED — advisory, evidence-backed, never applied."""
    snap = snapshot(db, workspace_id)
    out: list[PortfolioDecision] = []
    for cid, s in snap.channels.items():
        n = s["sample_size"]
        action, detail, conf = "KEEP", {}, 0.3
        if n < 6:
            action, detail, conf = "EXPERIMENT", {"reason": "cold start — accumulate data"}, 0.2
        elif s["scale_status"] == "SCALE" and n >= 12:
            action = "INCREASE_BUDGET"
            detail = {"suggested_delta_pct": 15, "cap": "workspace/brand/channel hard limits still apply"}
            conf = min(0.7, 0.35 + 0.02 * n)
        elif s["scale_status"] == "REVIEW":
            action = "REPOSITION_RECOMMENDED"
            detail = {"reason": "sustained underperformance", "keep_identity": True}
            conf = min(0.65, 0.3 + 0.02 * n)
        elif s["scale_status"] == "HOLD":
            action = "REDUCE_PRODUCTION"
            detail = {"suggested_delta_pct": -20}
            conf = 0.4
        row = PortfolioDecision(
            workspace_id=workspace_id, channel_id=cid, action=action, detail=detail,
            evidence={"scores": s, "objective": snap.objective},
            confidence=round(conf, 2), sample_size=n, applied=False,
        )
        db.add(row)
        out.append(row)
    db.flush()
    return out
