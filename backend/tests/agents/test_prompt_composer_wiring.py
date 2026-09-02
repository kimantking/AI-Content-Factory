"""AUDIT-P8-006 repair — the PromptComposer is on the real agent path.

Proves the production flow is
    Agent -> retrieve learning -> PromptComposer -> ModelExecutionGateway
    -> ModelRouter -> Provider
and that agent-/platform-/brand-specific retrieval, the context budget, the
disable switch and prompt-lineage telemetry all hold when driven from an agent
LLM call (not just the preview endpoint).
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest

from app.agents import model_gateway as gw
from app.db.base import session_scope
from app.db.models import Campaign
from app.db.models_learn import LearnedSkillNote, PromptBlueprint, ReferenceFeedback
from app.db.models_p8 import ModelRoutingEvent
from app.providers.base import LLMResponse

_APP = Path(__file__).resolve().parents[2] / "app"


class _CapturingProvider:
    """Records the FULL system prompt each routed call receives."""

    def __init__(self, name="mock", model="mock"):
        self.name = name
        self.model = model
        self.systems: list[str] = []

    def complete(self, *, system, user, task, context):
        self.systems.append(system)
        return LLMResponse(text=json.dumps({"ok": True, "confidence": 0.9}),
                           input_tokens=120, output_tokens=40, provider=self.name, model=self.model)


@pytest.fixture
def cap(monkeypatch):
    p = _CapturingProvider()
    from app.ai_router import execute as ex

    monkeypatch.setattr(ex, "_provider_for", lambda mid, prov: p)
    return p


def _campaign(db, *, ws, brand=None, platforms=("youtube_shorts",)):
    cid = str(uuid.uuid4())
    db.add(Campaign(id=cid, topic="AI가 바꾸는 직업", audience_goal="BALANCED",
                    platforms=list(platforms), status="RUNNING",
                    workspace_id=ws, brand_id=brand))
    db.flush()
    return cid


def _skill(db, *, ws, agent, rule, brand=None, platform="", status="CANDIDATE", conf=0.8):
    n = LearnedSkillNote(workspace_id=ws, brand_id=brand, agent_type=agent, skill_category="c",
                         rule=rule, confidence=conf, sample_size=6, status=status, platform=platform)
    db.add(n)
    db.flush()
    return n.id


def _bp(db, *, ws, agent, instr, brand=None, platforms=None, status="PROMOTED"):
    b = PromptBlueprint(workspace_id=ws, brand_id=brand, agent_type=agent, purpose="p",
                        instructions=[instr], constraints=["원문 복사 금지"], confidence=0.8,
                        sample_size=6, status=status, platforms=platforms or [])
    db.add(b)
    db.flush()
    return b.id


def _run(agent_name, task, *, cid, session):
    return gw.routed_complete(agent_name=agent_name, task=task, system="BASE_AGENT_PROMPT",
                              user="{}", context={}, session=session, campaign_id=cid,
                              workspace_id=None)


# --------------------------------------------------------------------------- #

def test_agent_prompt_uses_prompt_composer(cap, _base_settings):
    ws = str(uuid.uuid4())
    with session_scope() as db:
        cid = _campaign(db, ws=ws)
        _skill(db, ws=ws, agent="Hook Agent", rule="첫 3초에 promise를 제시한다")
        r = _run("Hook Agent", "hook", cid=cid, session=db)
    assert r.prompt_lineage["prompt_composer_used"] is True
    assert cap.systems and "## BASE" in cap.systems[0]
    assert "첫 3초에 promise를 제시한다" in cap.systems[0]


def test_relevant_learned_skill_is_injected(cap, _base_settings):
    ws = str(uuid.uuid4())
    with session_scope() as db:
        cid = _campaign(db, ws=ws)
        sid = _skill(db, ws=ws, agent="Research Agent",
                     rule="외부 URL 수치는 Fact Checker 통과 전엔 사실로 쓰지 않는다")
        r = _run("Research Agent", "research", cid=cid, session=db)
    assert "외부 URL 수치는 Fact Checker 통과 전엔 사실로 쓰지 않는다" in cap.systems[0]
    assert sid in r.prompt_lineage["skill_ids"]


def test_irrelevant_skill_not_injected(cap, _base_settings):
    ws = str(uuid.uuid4())
    with session_scope() as db:
        cid = _campaign(db, ws=ws)
        _skill(db, ws=ws, agent="Voice Director", rule="문장 사이 짧은 포즈")   # audio skill
        r = _run("Hook Agent", "hook", cid=cid, session=db)
    assert "문장 사이 짧은 포즈" not in cap.systems[0]
    assert r.prompt_lineage["skill_ids"] == []


def test_prompt_blueprint_agent_filter(cap, _base_settings):
    ws = str(uuid.uuid4())
    with session_scope() as db:
        cid = _campaign(db, ws=ws)
        _bp(db, ws=ws, agent="Hook Agent", instr="훅 블루프린트 지침")
        _bp(db, ws=ws, agent="Script Agent", instr="스크립트 블루프린트 지침")
        r = _run("Hook Agent", "hook", cid=cid, session=db)
    assert "훅 블루프린트 지침" in cap.systems[0]
    assert "스크립트 블루프린트 지침" not in cap.systems[0]


def test_prompt_blueprint_platform_filter(cap, _base_settings):
    ws = str(uuid.uuid4())
    with session_scope() as db:
        cid = _campaign(db, ws=ws, platforms=["youtube_long"])
        _bp(db, ws=ws, agent="Hook Agent", instr="틱톡 전용 지침", platforms=["tiktok"])
        _bp(db, ws=ws, agent="Hook Agent", instr="플랫폼 무관 지침", platforms=[])
        r = _run("Hook Agent", "hook", cid=cid, session=db)
    assert "플랫폼 무관 지침" in cap.systems[0]
    assert "틱톡 전용 지침" not in cap.systems[0]


def test_prompt_blueprint_brand_isolation(cap, _base_settings):
    ws = str(uuid.uuid4())
    brand_a, brand_b = str(uuid.uuid4()), str(uuid.uuid4())
    with session_scope() as db:
        cid_b = _campaign(db, ws=ws, brand=brand_b)
        _bp(db, ws=ws, agent="Hook Agent", instr="브랜드 A 전용 지침", brand=brand_a)
        _skill(db, ws=ws, agent="Hook Agent", rule="브랜드 A 전용 스킬", brand=brand_a)
        r = _run("Hook Agent", "hook", cid=cid_b, session=db)
    assert "브랜드 A 전용 지침" not in cap.systems[0]
    assert "브랜드 A 전용 스킬" not in cap.systems[0]
    assert r.prompt_lineage["skill_ids"] == [] and r.prompt_lineage["blueprint_ids"] == []


def test_disabled_skill_not_used(cap, _base_settings):
    ws = str(uuid.uuid4())
    with session_scope() as db:
        cid = _campaign(db, ws=ws)
        sid = _skill(db, ws=ws, agent="Hook Agent", rule="비활성화될 스킬 규칙")
        db.add(ReferenceFeedback(workspace_id=ws, skill_id=sid, actor="user", verdict="BLOCK"))
        db.flush()
        r = _run("Hook Agent", "hook", cid=cid, session=db)
    assert "비활성화될 스킬 규칙" not in cap.systems[0]
    assert r.prompt_lineage["skill_ids"] == []


def test_context_budget_enforced(cap, _base_settings):
    _base_settings.max_learned_context_tokens = 40
    _base_settings.max_learned_skills = 50
    ws = str(uuid.uuid4())
    with session_scope() as db:
        cid = _campaign(db, ws=ws)
        for i in range(30):
            _skill(db, ws=ws, agent="Hook Agent", rule=f"규칙 {i} " + "긴 설명 " * 10)
        r = _run("Hook Agent", "hook", cid=cid, session=db)
    assert 0 < len(r.prompt_lineage["skill_ids"]) < 30
    assert r.prompt_lineage["truncated"] is True


def test_prompt_lineage_recorded(cap, _base_settings):
    ws = str(uuid.uuid4())
    with session_scope() as db:
        cid = _campaign(db, ws=ws)
        sid = _skill(db, ws=ws, agent="Hook Agent", rule="라인리지 스킬")
        bid = _bp(db, ws=ws, agent="Hook Agent", instr="라인리지 블루프린트")
        _run("Hook Agent", "hook", cid=cid, session=db)
    with session_scope() as db:
        ev = db.query(ModelRoutingEvent).filter_by(campaign_id=cid).first()
        assert ev is not None and ev.prompt_lineage
        lin = dict(ev.prompt_lineage)
    assert lin["prompt_composer_used"] is True
    assert sid in lin["skill_ids"]
    assert bid in lin["blueprint_ids"]
    assert lin["prompt_version"] == "hook"
    assert lin["context_tokens"] > 0


def test_prompt_composer_then_model_gateway(cap, _base_settings):
    """Order: compose first (system carries LEARNED_GUIDANCE), THEN the router
    executes — the provider sees the composed prompt, and a routing event lands."""
    ws = str(uuid.uuid4())
    with session_scope() as db:
        cid = _campaign(db, ws=ws)
        _skill(db, ws=ws, agent="Hook Agent", rule="컴포저 우선 규칙")
        r = _run("Hook Agent", "hook", cid=cid, session=db)
    assert r.routed is True
    assert "LEARNED_GUIDANCE" in cap.systems[0] and "컴포저 우선 규칙" in cap.systems[0]
    with session_scope() as db:
        assert db.query(ModelRoutingEvent).filter_by(campaign_id=cid).count() == 1


def test_direct_provider_bypass_still_zero():
    """AUDIT-P8-001 must not regress: still no direct provider call in the
    production agent modules after the composer wiring."""
    for rel in ("agents/nodes.py", "agents/media_nodes.py", "autopilot/pipeline.py"):
        src = (_APP / rel).read_text(encoding="utf-8")
        assert not re.search(r"^[^#\n]*\bget_llm_provider\s*\(", src, re.M), rel
        assert not re.search(r"^from app\.providers\.(mock_llm|anthropic_llm|ollama_llm) import",
                             src, re.M), rel
