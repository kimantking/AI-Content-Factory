from __future__ import annotations

import pytest

from app.agents.runner import get_state, run_pipeline
from app.db.base import session_scope
from app.db.models import AgentRun, Campaign, ResearchSource
from app.providers.errors import ProviderError
from app.providers.faults import faults

TOPIC = "AI로 사라질 가능성이 높은 직업"


@pytest.fixture
def pg_checkpointer(_base_settings):
    _base_settings.checkpointer_kind = "postgres"
    return _base_settings


def test_pipeline_resumes_from_last_completed_node(make_campaign, pg_checkpointer):
    cid = make_campaign(topic=TOPIC)

    # 1) First run blows up inside fact_check (non-retryable), AFTER research + its
    #    checkpoint have been written.
    faults.arm("llm:fact_check", error_type="AUTH_ERROR", times=99)
    with pytest.raises(ProviderError):
        run_pipeline(cid, TOPIC, "BALANCED", ["YouTube"])

    with session_scope() as s:
        assert s.query(ResearchSource).filter_by(campaign_id=cid).count() >= 2
        research_runs_first = s.query(AgentRun).filter_by(
            campaign_id=cid, agent_name="Research Agent").count()
        assert research_runs_first == 1

    snap = get_state(cid)
    assert "fact_check" in snap["next"]  # stopped right before/at fact_check

    # 2) "Process restart": clear the fault, resume with the same thread_id.
    faults.clear()
    state = run_pipeline(cid, TOPIC, "BALANCED", ["YouTube"], resume=True)

    assert state["status"] == "SUCCESS"
    with session_scope() as s:
        camp = s.get(Campaign, cid)
        assert camp.status == "SUCCESS"
        # research did NOT run again -> resume skipped completed work
        research_runs_after = s.query(AgentRun).filter_by(
            campaign_id=cid, agent_name="Research Agent").count()
        assert research_runs_after == 1
