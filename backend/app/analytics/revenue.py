from __future__ import annotations

from sqlalchemy import func

from app.db.models import (
    AnalyticsSnapshot,
    CostAllocation,
    CostLog,
    Publication,
    RevenueEntry,
)

COST_KINDS = ["LLM", "SEARCH", "IMAGE", "VIDEO", "TTS", "STOCK", "MUSIC",
              "RENDER", "STORAGE", "PUBLISHING", "INFRA"]
REVENUE_SOURCES = ["PLATFORM_API", "AFFILIATE", "SPONSOR", "PRODUCT", "MANUAL", "ESTIMATE"]


def allocate_costs(session, campaign_id: str) -> int:
    """Roll cost_logs (Phase 1/1-B/2) into cost_allocations by kind. Idempotent."""
    have = {c.kind for c in session.query(CostAllocation).filter_by(campaign_id=campaign_id)
            if c.source_ref == "cost_logs:sum"}
    rows = (session.query(CostLog.kind, func.coalesce(func.sum(CostLog.amount_usd), 0.0))
            .filter(CostLog.campaign_id == campaign_id).group_by(CostLog.kind).all())
    n = 0
    for kind, amount in rows:
        k = (kind or "INFRA").upper()
        if k in have:
            continue
        session.add(CostAllocation(campaign_id=campaign_id, kind=k, amount=float(amount),
                                   currency="USD", source_ref="cost_logs:sum"))
        n += 1
    session.flush()
    return n


def revenue_breakdown(session, campaign_id: str) -> dict:
    rows = (session.query(RevenueEntry.source, RevenueEntry.is_estimate,
                          func.coalesce(func.sum(RevenueEntry.amount), 0.0))
            .filter(RevenueEntry.campaign_id == campaign_id)
            .group_by(RevenueEntry.source, RevenueEntry.is_estimate).all())
    by_source: dict[str, float] = {s: 0.0 for s in REVENUE_SOURCES}
    actual = estimate = 0.0
    for source, is_est, amount in rows:
        by_source[source] = by_source.get(source, 0.0) + float(amount)
        if is_est:
            estimate += float(amount)
        else:
            actual += float(amount)
    return {"by_source": by_source, "actual": round(actual, 4),
            "estimate": round(estimate, 4), "total": round(actual + estimate, 4)}


def cost_breakdown(session, campaign_id: str) -> dict:
    allocate_costs(session, campaign_id)
    rows = (session.query(CostAllocation.kind, func.coalesce(func.sum(CostAllocation.amount), 0.0))
            .filter(CostAllocation.campaign_id == campaign_id)
            .group_by(CostAllocation.kind).all())
    by_kind = {k: 0.0 for k in COST_KINDS}
    for kind, amount in rows:
        by_kind[kind] = by_kind.get(kind, 0.0) + float(amount)
    return {"by_kind": by_kind, "total": round(sum(by_kind.values()), 6)}


def profit_report(session, campaign_id: str) -> dict:
    rev = revenue_breakdown(session, campaign_id)
    cost = cost_breakdown(session, campaign_id)
    net = round(rev["total"] - cost["total"], 4)
    margin = round(net / rev["total"], 4) if rev["total"] else None

    views = int(session.query(func.coalesce(func.max(AnalyticsSnapshot.views), 0))
                .filter(AnalyticsSnapshot.campaign_id == campaign_id).scalar() or 0)
    followers = int(session.query(func.coalesce(func.sum(AnalyticsSnapshot.followers_gained), 0))
                    .filter(AnalyticsSnapshot.campaign_id == campaign_id).scalar() or 0)
    n_content = int(session.query(func.count(func.distinct(Publication.content_id)))
                    .filter(Publication.campaign_id == campaign_id).scalar() or 0) or 1

    def per_k(x: float) -> float | None:
        return round(x / (views / 1000.0), 4) if views else None

    return {
        "currency_note": "revenue mock KRW / cost USD — no FX applied in mock",
        "revenue": rev, "cost": cost, "net_profit": net, "margin": margin,
        "views_ref": views,
        "revenue_per_1000_views": per_k(rev["total"]),
        "profit_per_1000_views": per_k(net),
        "profit_per_content": round(net / n_content, 4),
        "cost_per_1000_views": per_k(cost["total"]),
        "cost_per_follower": round(cost["total"] / followers, 6) if followers else None,
    }
