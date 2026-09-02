from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.config import get_settings
from app.db.models import (
    AutopilotRun,
    Campaign,
    CostLog,
    Publication,
    TopicCandidate,
)


def check_watchdog(session, run: AutopilotRun) -> list[dict]:
    """Return a list of triggered watchdog conditions. Non-empty => the caller
    should pause the run."""
    s = get_settings()
    triggers: list[dict] = []
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    # 1. runaway cost (spend today across everything vs the HARD daily budget)
    spent_today = float(session.query(func.coalesce(func.sum(CostLog.amount_usd), 0.0))
                        .filter(CostLog.created_at >= day_ago).scalar() or 0.0)
    if spent_today > s.autopilot_daily_hard_budget_usd:
        triggers.append({"type": "RUNAWAY_COST", "detail": f"${spent_today:.2f} > hard ${s.autopilot_daily_hard_budget_usd}"})

    # 2. too many posts today
    posts_today = int(session.query(func.count(Publication.id))
                      .filter(Publication.created_at >= day_ago).scalar() or 0)
    if posts_today > s.autopilot_daily_post_limit:
        triggers.append({"type": "TOO_MANY_POSTS", "detail": f"{posts_today} > limit {s.autopilot_daily_post_limit}"})

    # 3. duplicate campaigns for the same candidate
    dup = (session.query(TopicCandidate.id, func.count(Campaign.id))
           .join(Campaign, Campaign.id == TopicCandidate.campaign_id)
           .filter(TopicCandidate.run_id == run.id)
           .group_by(TopicCandidate.id).having(func.count(Campaign.id) > 1).all())
    if dup:
        triggers.append({"type": "DUPLICATE_CAMPAIGN", "detail": f"{len(dup)} candidates map to >1 campaign"})

    # 4. high QA failure rate among this run's campaigns
    camp_ids = [c.campaign_id for c in
                session.query(TopicCandidate).filter_by(run_id=run.id)
                if c.campaign_id]
    if len(camp_ids) >= 3:
        failed = session.query(func.count(Campaign.id)).filter(
            Campaign.id.in_(camp_ids), Campaign.status == "FAILED").scalar() or 0
        if failed / len(camp_ids) > 0.5:
            triggers.append({"type": "HIGH_QA_FAILURE", "detail": f"{failed}/{len(camp_ids)} campaigns FAILED"})

    # 5. repeated publishing auth failure
    from app.db.models import PublishJob

    reauth = int(session.query(func.count(PublishJob.id))
                 .filter(PublishJob.status == "REAUTH_REQUIRED",
                         PublishJob.updated_at >= day_ago).scalar() or 0)
    if reauth >= 3:
        triggers.append({"type": "REPEATED_AUTH_FAILURE", "detail": f"{reauth} jobs REAUTH_REQUIRED"})

    return triggers
