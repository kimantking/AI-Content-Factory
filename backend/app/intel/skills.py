"""Agent Skill Learning — LearnedSkillNote + CreativeRecipe.

Learning is not stored only as a prompt string. A `LearnedSkillNote` is a small,
testable rule for one agent, with evidence ids, confidence and sample size. A
`CreativeRecipe` combines the best sub-profile from several references (Hook from
A, Story from B, Subtitle from C, ...).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models_learn import CreativeRecipe, LearnedSkillNote
from app.intel.router import AGENT_FOR_ANALYSIS

# analysis kind -> (skill_category, rule template) — deterministic, conservative
_SKILL_RULES = {
    "BROLL_PROFILE": ("visual_evidence", "숫자 Claim에는 generic B-roll보다 증거성 Visual(차트/문서)을 우선한다."),
    "GRAPHICS_PROFILE": ("data_viz", "통계·수치가 등장하면 데이터 시각화를 배치한다."),
    "AUDIO_PROFILE": ("audio_focus", "중요 CTA 직전 오디오 에너지를 낮춰 메시지 집중도를 확보한다."),
    "HOOK_PATTERN": ("hook", "첫 3초 내 핵심 시청 이유를 제시하되 과장 표현은 쓰지 않는다."),
    "EDITING_PROFILE": ("cut_rhythm", "정보 전환 지점마다 컷/비주얼을 전환해 시각적 리듬을 유지한다."),
    "SUBTITLE_PROFILE": ("caption", "핵심 단어를 하이라이트하고 한 줄 자막을 짧게 유지한다."),
    "VOICE_PROFILE": ("pacing", "문장 사이 짧은 포즈로 가독성을 확보한다."),
    "STORY_PROFILE": ("structure", "레퍼런스에서 반복 관측된 스토리 비트 순서를 우선 검토한다."),
    "WRITING_PROFILE": ("style", "짧은 문장 + 직접 화법을 섞되 원문 표현은 복사하지 않는다."),
    "RETENTION_PATTERN": ("retention", "도입부 시청 이유 + 중반 정보 밀도 유지. 리텐션 수치는 자체 Analytics로만 검증."),
    "FACTS": ("fact_discipline", "외부 URL의 수치·주장은 Fact Checker 통과 전까지 사실로 쓰지 않는다."),
    "KNOWLEDGE": ("explanation", "핵심 개념을 먼저 정의하고 예시로 뒷받침한 뒤 시각화 기회를 표시한다."),
    "GITHUB_ANALYSIS": ("technical_rights", "코드 라이선스는 콘텐츠 라이선스가 아니다 — 레포의 미디어를 그대로 쓰지 않는다."),
    "COMPETITOR_ANALYSIS": ("positioning", "경쟁 채널이 자주 쓰는 각도는 관찰용으로만 참고하고 모방하지 않는다."),
}


def derive_skill_notes(db: Session, *, workspace_id: str | None, brand_id: str | None,
                       channel_id: str | None, kind: str, evidence: list[dict],
                       consistency: float, platform: str = "", content_type: str = "",
                       topic_cluster: str = "") -> LearnedSkillNote | None:
    tmpl = _SKILL_RULES.get(kind)
    if not tmpl:
        return None
    sample_size = len({e.get("reference_id") for e in evidence if e.get("reference_id")}) or len(evidence)
    if sample_size < 1:
        return None
    category, rule = tmpl
    confidence = round(min(0.9, 0.3 + 0.05 * min(sample_size, 8) + 0.35 * consistency), 3)
    status = "OBSERVED" if sample_size <= 1 else ("EXPERIMENTAL" if sample_size < 3 else "CANDIDATE")
    note = LearnedSkillNote(
        workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id,
        agent_type=AGENT_FOR_ANALYSIS.get(kind, "Video Director"),
        skill_category=category, rule=rule,
        rationale=f"{kind} 특징이 {sample_size}개 레퍼런스에서 관측됨 (consistency={consistency:.2f}).",
        evidence_ids=[e.get("reference_id") for e in evidence if e.get("reference_id")],
        confidence=confidence, sample_size=sample_size,
        platform=platform, content_type=content_type, topic_cluster=topic_cluster,
        status=status,
    )
    db.add(note)
    db.flush()
    return note


def compose_creative_recipe(db: Session, *, workspace_id: str | None, brand_id: str | None,
                            channel_id: str | None, name: str, platform: str, content_type: str,
                            picks: dict) -> CreativeRecipe:
    """picks: {"hook_pattern": {...,"_ref": id}, "story_profile": {...}, ...} —
    each sub-profile can come from a different reference."""
    key_map = {
        "hook_pattern": "hook_pattern", "story_profile": "story_profile",
        "editing_profile": "editing_profile", "broll_profile": "broll_profile",
        "voice_profile": "voice_profile", "subtitle_profile": "subtitle_profile",
        "graphics_profile": "graphics_profile", "audio_profile": "audio_profile",
        "thumbnail_profile": "thumbnail_profile",
    }
    evidence_ids = sorted({v.get("_ref") for v in picks.values() if isinstance(v, dict) and v.get("_ref")})
    filled = sum(1 for k in key_map if picks.get(k))
    recipe = CreativeRecipe(
        workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id,
        name=name, platform=platform, content_type=content_type,
        confidence=round(min(0.9, 0.2 + 0.08 * filled + 0.05 * len(evidence_ids)), 3),
        evidence_ids=evidence_ids, status="OBSERVED",
        **{col: (picks.get(k) or {}) for k, col in key_map.items()},
    )
    db.add(recipe)
    db.flush()
    return recipe
