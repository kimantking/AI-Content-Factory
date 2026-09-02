from __future__ import annotations

import pytest

from app.db.base import session_scope
from app.providers.errors import NON_RETRYABLE
from app.services.budget import BudgetExceeded, campaign_spend, check_budget
from app.services.cost import log_cost


def test_budget_ok_under_limit(make_campaign, _base_settings):
    cid = make_campaign()
    _base_settings.campaign_budget_usd = 1.0
    with session_scope() as s:
        log_cost(s, campaign_id=cid, agent_name="x", kind="LLM", provider="mock", amount_usd=0.2)
    with session_scope() as s:
        check_budget(s, cid)  # should not raise
        assert campaign_spend(s, cid) == pytest.approx(0.2)


def test_campaign_budget_exceeded(make_campaign, _base_settings):
    cid = make_campaign()
    _base_settings.campaign_budget_usd = 0.5
    with session_scope() as s:
        log_cost(s, campaign_id=cid, agent_name="x", kind="LLM", provider="mock", amount_usd=0.4)
        log_cost(s, campaign_id=cid, agent_name="x", kind="LLM", provider="mock", amount_usd=0.4)
    with session_scope() as s, pytest.raises(BudgetExceeded) as ei:
        check_budget(s, cid)
    assert ei.value.scope == "campaign"


def test_budget_exceeded_is_non_retryable():
    assert "BUDGET_EXCEEDED" in NON_RETRYABLE
    assert BudgetExceeded("campaign", 1.0, 0.5).error_type == "BUDGET_EXCEEDED"


def test_pending_amount_is_considered(make_campaign, _base_settings):
    cid = make_campaign()
    _base_settings.daily_budget_usd = 1.0
    with session_scope() as s:
        log_cost(s, campaign_id=cid, agent_name="x", kind="LLM", provider="mock", amount_usd=0.9)
    with session_scope() as s, pytest.raises(BudgetExceeded):
        check_budget(s, cid, pending_usd=0.2)
