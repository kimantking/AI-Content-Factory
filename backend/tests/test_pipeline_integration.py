from __future__ import annotations

from app.agents.runner import run_pipeline
from app.db.base import session_scope
from app.db.models import (
    AgentRun,
    Campaign,
    CostLog,
    Hook,
    ResearchSource,
    Script,
    Strategy,
    VerifiedFact,
)

TOPIC = "AI로 사라질 가능성이 높은 직업"


def test_full_pipeline_persists_everything(make_campaign):
    cid = make_campaign(topic=TOPIC)
    state = run_pipeline(cid, TOPIC, "BALANCED", ["YouTube"])

    assert state["status"] == "SUCCESS"
    assert state["fact_score"] >= 0.6

    with session_scope() as s:
        camp = s.get(Campaign, cid)
        assert camp.status == "SUCCESS"
        assert camp.current_step == "done"
        assert camp.knowledge_pack["topic"] == TOPIC
        assert camp.knowledge_pack["verified_facts"]

        assert s.query(ResearchSource).filter_by(campaign_id=cid).count() >= 2
        facts = s.query(VerifiedFact).filter_by(campaign_id=cid).all()
        assert facts and all(f.status in {
            "VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED", "CONTRADICTED"} for f in facts)
        assert s.query(Strategy).filter_by(campaign_id=cid).count() == 1
        assert s.query(Hook).filter_by(campaign_id=cid).count() >= 3

        script = s.query(Script).filter_by(campaign_id=cid).first()
        assert script.qa_passed is True
        assert script.word_count > 30
        assert script.ai_slop_score <= 20
        assert script.cta_type
        assert script.naturalness["ai_slop_after"] <= script.naturalness["ai_slop_before"]

        runs = s.query(AgentRun).filter_by(campaign_id=cid).all()
        names = {r.agent_name for r in runs}
        assert {"Research Agent", "Fact Checker", "Content Strategist",
                "Hook Agent", "Script Agent", "Script QA"} <= names
        assert all(r.status == "SUCCESS" for r in runs)

        # cost logging present (mock = $0 but rows exist)
        assert s.query(CostLog).filter_by(campaign_id=cid).count() >= 6


def test_script_only_uses_usable_facts(make_campaign):
    cid = make_campaign(topic=TOPIC)
    run_pipeline(cid, TOPIC, "BALANCED", ["YouTube"])
    with session_scope() as s:
        script = s.query(Script).filter_by(campaign_id=cid).first()
        bad = s.query(VerifiedFact).filter(
            VerifiedFact.campaign_id == cid,
            VerifiedFact.status.in_(["UNVERIFIED", "CONTRADICTED"]),
        ).all()
        for f in bad:
            assert f.fact not in script.body


def test_research_fix_loop_runs_then_proceeds(make_campaign, _base_settings):
    # Force the fact score to always look insufficient so the router loops into
    # research_fix every time -> we verify the cap stops the loop (no infinite loop).
    _base_settings.fact_score_threshold = 1.01
    _base_settings.research_fix_max = 2
    cid = make_campaign(topic=TOPIC)
    state = run_pipeline(cid, TOPIC, "BALANCED", ["YouTube"])

    assert state["research_fix_count"] == 2  # capped, no infinite loop
    assert state["status"] in {"SUCCESS", "FAILED"}
    with session_scope() as s:
        runs = s.query(AgentRun).filter_by(campaign_id=cid, agent_name="Research Agent").count()
        assert runs == 3  # initial + 2 fixes
