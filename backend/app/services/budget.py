from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.config import get_settings
from app.db.models import CostLog


class BudgetExceeded(Exception):
    error_type = "BUDGET_EXCEEDED"

    def __init__(self, scope: str, spent: float, limit: float):
        self.scope = scope
        self.spent = spent
        self.limit = limit
        super().__init__(f"{scope} budget exceeded: ${spent:.4f} / ${limit:.2f}")


def _sum(session, *filters) -> float:
    q = session.query(func.coalesce(func.sum(CostLog.amount_usd), 0.0))
    for f in filters:
        q = q.filter(f)
    return float(q.scalar() or 0.0)


def campaign_spend(session, campaign_id: str) -> float:
    return _sum(session, CostLog.campaign_id == campaign_id)


def daily_spend(session) -> float:
    start = datetime.now(timezone.utc) - timedelta(days=1)
    return _sum(session, CostLog.created_at >= start)


def monthly_spend(session) -> float:
    start = datetime.now(timezone.utc) - timedelta(days=30)
    return _sum(session, CostLog.created_at >= start)


MEDIA_KINDS = ("IMAGE", "VIDEO", "TTS", "STOCK", "MUSIC", "RENDER")


def media_spend(session, campaign_id: str) -> float:
    return _sum(session, CostLog.campaign_id == campaign_id, CostLog.kind.in_(MEDIA_KINDS))


def check_media_budget(session, campaign_id: str, *, pending_usd: float = 0.0) -> None:
    """Media sub-budget (separate from the Phase 1-A LLM budget). Non-retryable."""
    s = get_settings()
    spent = media_spend(session, campaign_id) + pending_usd
    if s.media_budget_usd >= 0 and spent > s.media_budget_usd:
        raise BudgetExceeded("media", spent, s.media_budget_usd)
    # media also counts toward the campaign/daily/monthly envelopes
    check_budget(session, campaign_id, pending_usd=pending_usd)


def check_budget(session, campaign_id: str, *, pending_usd: float = 0.0) -> None:
    """Raise BudgetExceeded if adding pending_usd would break any limit.

    BUDGET_EXCEEDED is non-retryable by design (see providers.errors.NON_RETRYABLE).
    """
    s = get_settings()
    checks = [
        ("campaign", campaign_spend(session, campaign_id) + pending_usd, s.campaign_budget_usd),
        ("daily", daily_spend(session) + pending_usd, s.daily_budget_usd),
        ("monthly", monthly_spend(session) + pending_usd, s.monthly_budget_usd),
    ]
    for scope, spent, limit in checks:
        if limit >= 0 and spent > limit:
            raise BudgetExceeded(scope, spent, limit)
