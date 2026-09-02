"""AUDIT-P6-001 — cross-channel capacity planner.

Deterministic, budget-aware daily production capacity per channel:
    remaining_slots = max(0, daily_max_posts - used_today)
    budget_headroom = max(0, daily_budget_usd - spent_today)
where `used_today` counts campaigns created today for the channel plus publish
jobs scheduled/published today, and `spent_today` sums today's CostLog + Asset
cost for those campaigns.

`portfolio_capacity` aggregates it into a single `max_new_campaigns` number the
Autopilot controller uses to cap a selection, and
`GET /api/publishing/calendar/capacity` surfaces the same model to the calendar UI.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func as safunc
from sqlalchemy.orm import Session

from app.db.models import Asset, Campaign, CostLog, PublishJob
from app.db.models_mb import Channel

_ACTIVE_JOB = ("SCHEDULED", "QUEUED", "READY", "WAITING_APPROVAL", "PUBLISHING", "PUBLISHED", "VERIFYING")


def _day_bounds(day: datetime | None = None) -> tuple[datetime, datetime]:
    now = day or datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _spent_today(db: Session, campaign_ids: list[str], start: datetime, end: datetime) -> float:
    if not campaign_ids:
        return 0.0
    c = db.query(safunc.coalesce(safunc.sum(CostLog.amount_usd), 0.0)).filter(
        CostLog.campaign_id.in_(campaign_ids),
        CostLog.created_at >= start, CostLog.created_at < end).scalar() or 0.0
    a = db.query(safunc.coalesce(safunc.sum(Asset.cost), 0.0)).filter(
        Asset.campaign_id.in_(campaign_ids),
        Asset.created_at >= start, Asset.created_at < end).scalar() or 0.0
    return round(float(c) + float(a), 4)


def channel_capacity(db: Session, *, workspace_id: str | None = None,
                     day: datetime | None = None) -> list[dict]:
    start, end = _day_bounds(day)
    q = db.query(Channel).filter(Channel.status == "ACTIVE")
    if workspace_id:
        q = q.filter(Channel.workspace_id == workspace_id)
    out: list[dict] = []
    for ch in q.all():
        camp_ids = [c.id for c in db.query(Campaign.id).filter(
            Campaign.channel_id == ch.id, Campaign.created_at >= start, Campaign.created_at < end)]
        jobs_today = db.query(safunc.count(PublishJob.id)).join(
            Campaign, PublishJob.campaign_id == Campaign.id).filter(
            Campaign.channel_id == ch.id, PublishJob.status.in_(_ACTIVE_JOB),
            PublishJob.scheduled_at >= start, PublishJob.scheduled_at < end).scalar() or 0
        used = max(len(camp_ids), int(jobs_today))
        cap = int(ch.daily_max_posts or 0)
        spent = _spent_today(db, camp_ids, start, end)
        budget = float(ch.daily_budget_usd or 0.0)
        headroom = round(budget - spent, 4) if budget > 0 else None
        out.append({
            "channel_id": ch.id, "name": ch.name, "platform": ch.platform,
            "daily_max_posts": cap, "daily_min_posts": int(ch.daily_min_posts or 0),
            "used_today": used,
            "remaining_slots": max(0, cap - used),
            "daily_budget_usd": budget or None, "spent_today_usd": spent,
            "budget_headroom_usd": headroom,
            "budget_blocked": headroom is not None and headroom <= 0,
            "autopilot_mode": ch.autopilot_mode,
        })
    return out


def portfolio_capacity(db: Session, *, workspace_id: str | None = None,
                       fallback_max: int = 0, day: datetime | None = None) -> dict:
    """Aggregate remaining capacity. When no channels are configured, fall back to
    `fallback_max` (the existing autopilot_daily_content_max) so single-stream
    autopilot is unchanged."""
    rows = channel_capacity(db, workspace_id=workspace_id, day=day)
    if not rows:
        return {"channels": 0, "max_new_campaigns": fallback_max,
                "remaining_slots": fallback_max, "budget_blocked_channels": 0,
                "per_channel": [], "source": "fallback"}
    remaining = sum(r["remaining_slots"] for r in rows
                    if not r["budget_blocked"] and r["autopilot_mode"] != "OFF")
    return {
        "channels": len(rows),
        "remaining_slots": remaining,
        "max_new_campaigns": remaining,
        "budget_blocked_channels": sum(1 for r in rows if r["budget_blocked"]),
        "min_posts_shortfall": sum(max(0, r["daily_min_posts"] - r["used_today"]) for r in rows),
        "per_channel": rows,
        "source": "channels",
    }
