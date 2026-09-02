"""§AI-§AM / §BI-§BL — PromptComposer: agent- and platform-specific retrieval,
context budget, production strictness."""
from __future__ import annotations

import uuid

from app.db.base import session_scope
from app.db.models_learn import LearnedSkillNote, PromptBlueprint
from app.intel.composer import compose, relevant_blueprints, relevant_skills


def _skill(db, ws, agent, rule, *, status="CANDIDATE", platform="", conf=0.7):
    n = LearnedSkillNote(workspace_id=ws, agent_type=agent, skill_category="c", rule=rule,
                         confidence=conf, sample_size=5, status=status, platform=platform)
    db.add(n)
    db.flush()
    return n.id


def _bp(db, ws, agent, instr, *, status="CANDIDATE", platforms=None):
    b = PromptBlueprint(workspace_id=ws, agent_type=agent, purpose="p", instructions=[instr],
                        constraints=["원문 복사 금지"], confidence=0.7, sample_size=5,
                        status=status, platforms=platforms or [])
    db.add(b)
    db.flush()
    return b.id


def test_agent_specific_retrieval():
    ws = str(uuid.uuid4())
    with session_scope() as db:
        _skill(db, ws, "Hook Agent", "훅은 3초 안에 promise")
        _skill(db, ws, "B-roll Director", "숫자엔 증거 비주얼")
        _skill(db, ws, "Audio Director", "CTA 직전 오디오 다운")
        hook = [s.agent_type for s in relevant_skills(db, workspace_id=ws, agent_type="Hook Agent")]
        broll = [s.agent_type for s in relevant_skills(db, workspace_id=ws, agent_type="B-roll Director")]
    assert hook == ["Hook Agent"]
    assert broll == ["B-roll Director"]


def test_platform_specific_retrieval():
    ws = str(uuid.uuid4())
    with session_scope() as db:
        _bp(db, ws, "Video Editor", "틱톡용 빠른 컷", platforms=["tiktok"])
        _bp(db, ws, "Video Editor", "플랫폼 무관 리듬", platforms=[])
        yt = relevant_blueprints(db, workspace_id=ws, agent_type="Video Editor",
                                 platform="youtube_long", include_experimental=True)
        instrs = {i for b in yt for i in b.instructions}
    assert "플랫폼 무관 리듬" in instrs
    assert "틱톡용 빠른 컷" not in instrs         # tiktok-only not force-applied to YT long


def test_context_budget_truncates(_base_settings):
    _base_settings.max_learned_context_tokens = 60
    _base_settings.max_learned_skills = 50
    ws = str(uuid.uuid4())
    with session_scope() as db:
        for i in range(30):
            _skill(db, ws, "Video Director", f"규칙 {i}: " + "긴 설명 문장 " * 12)
        out = compose(db, agent_type="Video Director", base_prompt="base",
                      workspace_id=ws, include_experimental=True)
    assert out["learned_tokens"] <= out["budget"]
    assert out["truncated"] is True
    assert 0 < len(out["used_skills"]) < 30


def test_production_default_only_injects_promoted_blueprints():
    ws = str(uuid.uuid4())
    with session_scope() as db:
        _bp(db, ws, "Script Agent", "실험 지침", status="EXPERIMENTAL")
        _bp(db, ws, "Script Agent", "승격된 지침", status="PROMOTED")
        strict = {b.status for b in relevant_blueprints(
            db, workspace_id=ws, agent_type="Script Agent", include_experimental=False)}
        lab = {b.status for b in relevant_blueprints(
            db, workspace_id=ws, agent_type="Script Agent", include_experimental=True)}
    assert strict == {"PROMOTED"}
    assert lab >= {"EXPERIMENTAL", "PROMOTED"}


def test_compose_includes_all_sections():
    ws = str(uuid.uuid4())
    with session_scope() as db:
        _skill(db, ws, "Script Agent", "직접 화법 사용")
        out = compose(db, agent_type="Script Agent", base_prompt="에이전트 기본 프롬프트",
                      workspace_id=ws, brand_context="브랜드 톤: 차분함",
                      channel_context="채널: 경제", memory_context="과거: 질문형 훅이 잘됨",
                      include_experimental=True)
    for sec in ("BASE", "BRAND", "CHANNEL", "MEMORY", "LEARNED_GUIDANCE"):
        assert sec in out["sections"]
    assert "에이전트 기본 프롬프트" in out["prompt"]
