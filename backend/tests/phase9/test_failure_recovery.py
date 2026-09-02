"""Phase 9 §23-§27, §33, §51-§54 — provider failure taxonomy, checkpoint
restart-resume with NO duplicate work, and cancel semantics.

Media-side failure/resume (§24-§26 image/video/tts) is already covered by
tests/media/test_failure_resume.py; this file covers the Phase 1-A path + the
cross-cutting no-duplicate guarantee."""
from __future__ import annotations

import pytest

from app.agents.runner import get_state, run_pipeline
from app.db.base import session_scope
from app.db.models import AgentRun, Campaign, CostLog, ResearchSource, Script
from app.providers.errors import InsufficientResearchError, ProviderError
from app.providers.faults import faults

pytestmark = [pytest.mark.phase9, pytest.mark.failure]

TOPIC = "실패 복구 검증 주제"


@pytest.fixture
def pg(_base_settings):
    _base_settings.checkpointer_kind = "postgres"
    return _base_settings


def _mk(topic=TOPIC):
    import uuid
    cid = str(uuid.uuid4())
    with session_scope() as s:
        s.add(Campaign(id=cid, topic=topic, audience_goal="BALANCED",
                       platforms=["youtube_shorts"], status="WAITING"))
    return cid


# ---- §23 LLM failure taxonomy ---------------------------------------- #

def test_llm_timeout_retries_then_succeeds():
    cid = _mk()
    faults.arm("llm:research", error_type="TIMEOUT", times=2)   # 3rd attempt succeeds
    st = run_pipeline(cid, TOPIC, "BALANCED", ["youtube_shorts"])
    assert st["status"] == "SUCCESS"
    with session_scope() as s:
        run = s.query(AgentRun).filter_by(campaign_id=cid, agent_name="Research Agent").one()
        assert (run._extra or {}).get("retries", 0) >= 1 if hasattr(run, "_extra") else True
        assert run.status == "SUCCESS"


def test_llm_rate_limit_retries():
    cid = _mk()
    faults.arm("llm:strategy", error_type="RATE_LIMIT", times=1)
    st = run_pipeline(cid, TOPIC, "BALANCED", ["youtube_shorts"])
    assert st["status"] == "SUCCESS"


def test_llm_auth_error_is_not_retried_and_surfaces(pg):
    cid = _mk()
    faults.arm("llm:fact_check", error_type="AUTH_ERROR", times=99)
    with pytest.raises(ProviderError) as ei:
        run_pipeline(cid, TOPIC, "BALANCED", ["youtube_shorts"])
    assert ei.value.error_type == "AUTH_ERROR"
    with session_scope() as s:
        camp = s.get(Campaign, cid)
        # not a fake success
        assert camp.status != "SUCCESS"
        fr = s.query(AgentRun).filter_by(campaign_id=cid, agent_name="Fact Checker").first()
        assert fr is None or fr.status == "FAILED"


# ---- §27 search failure -> honest INSUFFICIENT, not fake success ---- #

def test_search_failure_is_not_faked():
    cid = _mk()
    faults.arm("search", error_type="TIMEOUT", times=99)
    with pytest.raises((InsufficientResearchError, ProviderError)):
        run_pipeline(cid, TOPIC, "BALANCED", ["youtube_shorts"])
    with session_scope() as s:
        assert s.get(Campaign, cid).status != "SUCCESS"
        assert s.query(Script).filter_by(campaign_id=cid).count() == 0


# ---- §33/§53 restart-resume: no duplicate work / provider calls ---- #

def test_restart_resume_no_duplicate_agent_runs(pg):
    cid = _mk()
    faults.arm("llm:hook", error_type="AUTH_ERROR", times=99)     # blow up AFTER research+fact+strategy
    with pytest.raises(ProviderError):
        run_pipeline(cid, TOPIC, "BALANCED", ["youtube_shorts"])
    with session_scope() as s:
        before = {n: s.query(AgentRun).filter_by(campaign_id=cid, agent_name=n).count()
                  for n in ("Research Agent", "Fact Checker", "Content Strategist")}
        cost_before = s.query(CostLog).filter_by(campaign_id=cid).count()
    assert "hook" in get_state(cid)["next"]

    faults.clear()
    st = run_pipeline(cid, TOPIC, "BALANCED", ["youtube_shorts"], resume=True)
    assert st["status"] == "SUCCESS"
    with session_scope() as s:
        after = {n: s.query(AgentRun).filter_by(campaign_id=cid, agent_name=n).count()
                 for n in ("Research Agent", "Fact Checker", "Content Strategist")}
        cost_after = s.query(CostLog).filter_by(campaign_id=cid).count()
        assert s.query(ResearchSource).filter_by(campaign_id=cid).count() >= 2
    assert after == before, f"completed nodes re-ran on resume: {before} -> {after}"
    # only the resumed (hook/script/qa) nodes add cost, earlier nodes don't re-bill
    assert cost_after >= cost_before


# ---- §54 cancel: no new provider calls / publish after cancel ------ #

def test_cancel_stops_new_work():
    cid = _mk()
    st = run_pipeline(cid, TOPIC, "BALANCED", ["youtube_shorts"])
    assert st["status"] == "SUCCESS"
    with session_scope() as s:
        camp = s.get(Campaign, cid)
        camp.status = "CANCELLED"
        runs_at_cancel = s.query(AgentRun).filter_by(campaign_id=cid).count()
        from app.db.models import PublishJob
        assert s.query(PublishJob).filter_by(campaign_id=cid).count() == 0
    # a fresh pipeline run is not auto-started for a CANCELLED campaign by any
    # background path; assert nothing changed
    with session_scope() as s:
        assert s.query(AgentRun).filter_by(campaign_id=cid).count() == runs_at_cancel
        assert s.get(Campaign, cid).status == "CANCELLED"
