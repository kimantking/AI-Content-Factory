from __future__ import annotations

import pytest

from app.agents.runner import run_pipeline
from app.db.base import session_scope
from app.db.models import AgentRun, Campaign
from app.providers.errors import AuthError, ProviderError
from app.providers.faults import faults
from app.providers.retry import call_with_retry

TOPIC = "AI로 사라질 가능성이 높은 직업"


def test_call_with_retry_succeeds_after_transient_failure():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ProviderError("boom", error_type="TIMEOUT")
        return "ok"

    assert call_with_retry(flaky, attempts=3) == "ok"
    assert calls["n"] == 2


def test_call_with_retry_does_not_retry_auth_error():
    calls = {"n": 0}

    def bad():
        calls["n"] += 1
        raise AuthError("nope")

    with pytest.raises(AuthError):
        call_with_retry(bad, attempts=5)
    assert calls["n"] == 1


def test_pipeline_recovers_when_search_fails_once(make_campaign):
    # First Research provider call fails, retry succeeds.
    faults.arm("search", error_type="PROVIDER_ERROR", times=1)
    cid = make_campaign(topic=TOPIC)
    state = run_pipeline(cid, TOPIC, "BALANCED", ["YouTube"])

    assert state["status"] == "SUCCESS"
    with session_scope() as s:
        camp = s.get(Campaign, cid)
        assert camp.status == "SUCCESS"
        research_runs = s.query(AgentRun).filter_by(
            campaign_id=cid, agent_name="Research Agent").all()
        # the node itself succeeded (retry was internal)
        assert research_runs and research_runs[0].status == "SUCCESS"


def test_pipeline_fails_hard_on_auth_error(make_campaign):
    faults.arm("llm:research", error_type="AUTH_ERROR", times=5)
    cid = make_campaign(topic=TOPIC)
    with pytest.raises(ProviderError):
        run_pipeline(cid, TOPIC, "BALANCED", ["YouTube"])
    with session_scope() as s:
        run = s.query(AgentRun).filter_by(campaign_id=cid, agent_name="Research Agent").first()
        assert run.status == "FAILED"
        assert run.error_type == "AUTH_ERROR"
