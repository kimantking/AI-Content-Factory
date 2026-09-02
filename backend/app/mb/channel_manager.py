"""Channel Manager (§12-§18, §99) — deterministic.

ChannelHealthScore + ChannelOperatingPlan from SQL/metrics/rules. No LLM call in
the hot path (§102). Warmup + false-optimization guards from Phase 3 rules (§16,
§93, §94).
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Campaign, CostLog, PerformanceScore, RevenueEntry
from app.db.models_mb import (
    Channel,
    ChannelHealthSnapshot,
    ChannelOperatingPlan,
    ContentPillar,
)

_MIN_SAMPLE_SCALE = 12          # < this => never a confident SCALE
_MIN_SAMPLE_MODERATE = 6

SCALE_STATUS = ("NOT_ENOUGH_DATA", "HOLD", "TEST_MORE", "SCALE_CAUTIOUSLY", "SCALE", "REVIEW")


def _now():
    return datetime.now(timezone.utc)


def _channel_campaigns(db: Session, channel_id: str, *, days: int = 90) -> list[Campaign]:
    cut = _now() - timedelta(days=days)
    return (db.query(Campaign)
            .filter(Campaign.channel_id == channel_id, Campaign.created_at >= cut)
            .all())


def _channel_costs(db: Session, channel_id: str, *, days: int = 30) -> float:
    cut = _now() - timedelta(days=days)
    q = (db.query(func.coalesce(func.sum(CostLog.amount_usd), 0.0))
         .filter(CostLog.channel_id == channel_id, CostLog.created_at >= cut))
    return float(q.scalar() or 0.0)


def _channel_revenue(db: Session, channel_id: str, *, days: int = 30,
                     estimate: bool | None = None) -> float:
    cut = _now() - timedelta(days=days)
    q = (db.query(func.coalesce(func.sum(RevenueEntry.amount), 0.0))
         .filter(RevenueEntry.channel_id == channel_id, RevenueEntry.occurred_at >= cut))
    if estimate is not None:
        q = q.filter(RevenueEntry.is_estimate == estimate)
    return float(q.scalar() or 0.0)


def _perf_scores(db: Session, channel_id: str) -> list[PerformanceScore]:
    camp_ids = [c.id for c in db.query(Campaign.id).filter(Campaign.channel_id == channel_id)]
    if not camp_ids:
        return []
    # PerformanceScore.content_id links to platform content; approximate via campaign join is
    # out of scope here — use whatever rows reference these campaigns' contents.
    return (db.query(PerformanceScore)
            .filter(PerformanceScore.content_id.in_(
                [cid for cid in _content_ids_for(db, camp_ids)]))
            .all()) if camp_ids else []


def _content_ids_for(db: Session, campaign_ids: list[str]) -> list[str]:
    from app.db.models import PlatformContent
    return [r[0] for r in db.query(PlatformContent.id)
            .filter(PlatformContent.campaign_id.in_(campaign_ids)).all()]


def health_score(db: Session, channel: Channel) -> ChannelHealthSnapshot:
    camps = _channel_campaigns(db, channel.id)
    n = len(camps)
    published = [c for c in camps if c.status in ("SUCCESS",)]
    scores = _perf_scores(db, channel.id)
    perf_vals = [s.score for s in scores if not (s.is_outlier or s.has_anomaly)]
    cost30 = _channel_costs(db, channel.id, days=30)
    rev30_actual = _channel_revenue(db, channel.id, days=30, estimate=False)

    comp: dict[str, float] = {}
    # activity: any campaigns in last 30d
    recent = [c for c in camps if c.created_at >= _now() - timedelta(days=30)]
    comp["activity"] = min(100.0, len(recent) * 12.0)
    # publishing reliability: SUCCESS / attempted
    comp["publishing_reliability"] = round(100.0 * (len(published) / n), 1) if n else 0.0
    # content performance: mean relative score (already channel/relative in Phase 3)
    comp["content_performance"] = round(min(100.0, statistics.fmean(perf_vals)), 1) if perf_vals else 0.0
    # audience growth: no follower series wired yet -> 0 / unknown
    comp["audience_growth"] = 0.0
    # revenue / profit / efficiency
    comp["revenue"] = round(min(100.0, rev30_actual / 10.0), 1)          # $ scale placeholder
    profit = rev30_actual - cost30
    comp["profit"] = round(max(0.0, min(100.0, 50.0 + profit / 5.0)), 1)
    comp["cost_efficiency"] = round(max(0.0, min(100.0, 100.0 - cost30 / 2.0)), 1)
    # topic diversity: distinct topic clusters among campaigns
    clusters = {getattr(c, "topic", "")[:12] for c in camps}
    comp["topic_diversity"] = round(min(100.0, len(clusters) * 14.0), 1)
    # brand consistency + policy/account health: no violations recorded -> assume OK
    comp["brand_consistency"] = 80.0
    comp["policy_health"] = 90.0
    comp["account_health"] = 90.0 if channel.platform_account_id else 60.0

    # weighted by the channel's objective
    obj = (channel.primary_objective or "BALANCED").upper()
    weights = {
        "GROWTH": {"activity": .18, "content_performance": .22, "audience_growth": .22,
                   "publishing_reliability": .12, "topic_diversity": .10,
                   "policy_health": .08, "account_health": .08},
        "REVENUE": {"revenue": .30, "content_performance": .18, "publishing_reliability": .12,
                    "policy_health": .12, "account_health": .12, "cost_efficiency": .16},
        "PROFIT": {"profit": .32, "cost_efficiency": .20, "revenue": .16,
                   "content_performance": .14, "publishing_reliability": .10, "policy_health": .08},
        "BALANCED": {"activity": .12, "publishing_reliability": .12, "content_performance": .16,
                     "audience_growth": .12, "revenue": .10, "profit": .10,
                     "cost_efficiency": .10, "topic_diversity": .06, "brand_consistency": .06,
                     "policy_health": .03, "account_health": .03},
    }.get(obj, None)
    if weights is None:
        weights = {k: 1.0 / len(comp) for k in comp}
    total_w = sum(weights.get(k, 0.0) for k in comp) or 1.0
    score = sum(comp[k] * weights.get(k, 0.0) for k in comp) / total_w

    scale_status = _scale_status(n, perf_vals)
    snap = ChannelHealthSnapshot(
        channel_id=channel.id, workspace_id=channel.workspace_id,
        score=round(score, 1), components={k: round(v, 1) for k, v in comp.items()},
        lifecycle=channel.lifecycle, scale_status=scale_status, sample_size=n,
    )
    db.add(snap)
    db.flush()
    return snap


def _scale_status(sample: int, perf_vals: list[float]) -> str:
    if sample < _MIN_SAMPLE_MODERATE:
        return "NOT_ENOUGH_DATA"
    if not perf_vals or len(perf_vals) < _MIN_SAMPLE_MODERATE:
        return "TEST_MORE"
    med = statistics.median(perf_vals)
    # a single viral outlier can't drive SCALE (§114): require the median (not max) to be strong
    if sample < _MIN_SAMPLE_SCALE:
        return "SCALE_CAUTIOUSLY" if med >= 62 else "TEST_MORE"
    if med >= 68:
        return "SCALE"
    if med >= 55:
        return "SCALE_CAUTIOUSLY"
    if med < 40:
        return "REVIEW"
    return "HOLD"


def operating_plan(db: Session, channel: Channel, snap: ChannelHealthSnapshot | None = None
                   ) -> ChannelOperatingPlan:
    snap = snap or health_score(db, channel)
    pillars = db.query(ContentPillar).filter_by(brand_id=channel.brand_id, status="ACTIVE").all()
    is_warmup = channel.lifecycle in ("DRAFT", "WARMUP") or snap.sample_size < _MIN_SAMPLE_MODERATE

    if is_warmup:
        content_mix = {"CORE": .30, "TREND": .20, "EVERGREEN": .20,
                       "EXPERIMENT": .25, "REVENUE": .05}
        production_profile = "STANDARD" if channel.production_profile == "CINEMATIC" else channel.production_profile
        notes = ["WARMUP: diverse topics / hooks / durations, controlled experiments, "
                 "no high-confidence optimisation until data accrues"]
    else:
        content_mix = channel.content_strategy.get("content_mix") or {
            "CORE": .35, "TREND": .25, "EVERGREEN": .20, "EXPERIMENT": .10, "REVENUE": .10}
        production_profile = channel.production_profile
        notes = []

    # content target: bounded by daily_min/max and by scale status
    base_target = channel.daily_max_posts
    if snap.scale_status in ("REVIEW", "HOLD"):
        base_target = max(channel.daily_min_posts, channel.daily_max_posts - 1)
    elif snap.scale_status == "SCALE" and channel.daily_max_posts < 5:
        base_target = channel.daily_max_posts  # scaling is a portfolio decision, not auto here
    content_target = max(channel.daily_min_posts, min(base_target, channel.daily_max_posts))

    plan = {
        "channel_id": channel.id,
        "objective": channel.primary_objective,
        "lifecycle": channel.lifecycle,
        "warmup": is_warmup,
        "content_target": content_target,
        "topic_preferences": [p.name for p in pillars] or channel.content_strategy.get("topics", []),
        "content_mix": content_mix,
        "production_profile": production_profile,
        "daily_budget_usd": channel.daily_budget_usd,
        "publish_windows": channel.schedule.get("publish_windows", []),
        "growth_goal": channel.content_strategy.get("growth_goal"),
        "revenue_goal": channel.content_strategy.get("revenue_goal"),
        "scale_status": snap.scale_status,
        "health_score": snap.score,
        "recommended_actions": _recommended_actions(snap, is_warmup),
        "risks": _risks(db, channel, snap),
    }
    row = ChannelOperatingPlan(
        channel_id=channel.id, workspace_id=channel.workspace_id, plan=plan,
        evidence={"sample_size": snap.sample_size, "components": snap.components,
                  "notes": notes},
    )
    db.add(row)
    db.flush()
    return row


def _recommended_actions(snap: ChannelHealthSnapshot, warmup: bool) -> list[str]:
    if warmup:
        return ["accumulate_data", "run_controlled_experiments"]
    acts = []
    c = snap.components
    if c.get("publishing_reliability", 100) < 70:
        acts.append("fix_publishing_reliability")
    if c.get("topic_diversity", 100) < 40:
        acts.append("broaden_topic_pillars")
    if c.get("cost_efficiency", 100) < 40:
        acts.append("lower_production_profile")
    if snap.scale_status == "SCALE":
        acts.append("propose_scale_to_portfolio")
    if snap.scale_status == "REVIEW":
        acts.append("reposition_review_recommended")
    return acts or ["continue"]


def _risks(db: Session, channel: Channel, snap: ChannelHealthSnapshot) -> list[str]:
    risks = []
    if snap.components.get("account_health", 100) < 70:
        risks.append("no_platform_account_connected")
    if snap.components.get("content_performance", 100) < 35 and snap.sample_size >= 8:
        risks.append("sustained_underperformance")
    return risks
