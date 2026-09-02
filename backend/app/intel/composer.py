"""PromptComposer — assemble an agent prompt from Base + Brand + Channel + Memory
+ the most relevant Learned Skills + Prompt Blueprints, under a context budget.

Agent-specific retrieval: a Hook Agent gets hook patterns, not editing profiles.
Platform-specific retrieval: a TikTok reference is not force-applied to a YouTube
long-form. Learned prompts DO NOT reach production automatically
(`auto_promote_learned_prompts` is false) — only PROMOTED blueprints, or ones the
caller explicitly opts into, are injected.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models_learn import LearnedSkillNote, PromptBlueprint, ReferenceFeedback

# a user "disables" a learned skill / blueprint by leaving feedback with one of
# these verdicts — the composer then never injects it (spec §13).
_DISABLE_VERDICTS = ("BLOCK", "NOT_USEFUL", "WRONG")

# agent_type -> the analysis-derived agents whose skills/blueprints are relevant
_AGENT_ALIASES = {
    "Research Agent": {"Research Agent"},
    "Fact Checker": {"Research Agent", "Fact Checker"},
    "Strategist": {"Strategist"},
    "Hook Agent": {"Hook Agent"},
    "Script Agent": {"Script Agent", "Story Director"},
    "Story Director": {"Story Director", "Script Agent"},
    "Video Director": {"Video Director", "Retention Director", "Story Director"},
    "Retention Director": {"Retention Director", "Video Director"},
    "Scene Planner": {"Video Director", "Story Director"},
    "Shot Director": {"Video Editor", "Video Director"},
    "Visual Director": {"Visual Director", "B-roll Director", "Graphics Director"},
    "B-roll Director": {"B-roll Director", "Visual Director"},
    "Motion Director": {"Video Editor"},
    "Graphics Director": {"Graphics Director"},
    "Voice Director": {"Voice Director"},
    "Audio Director": {"Audio Director"},
    "Subtitle Director": {"Subtitle Director"},
    "Video Editor": {"Video Editor"},
    "Thumbnail Director": {"Thumbnail Director"},
    "Platform Adapter": {"Strategist"},
}

_INJECTABLE_STATUS = {"PROMOTED", "VALIDATED", "CANDIDATE"}


def _tok(text: str) -> int:
    return max(1, round(len(text) / 4))


def _platform_ok(row_platforms: list[str], platform: str | None, content_type: str | None) -> bool:
    if not platform or not row_platforms:
        return True
    return platform in row_platforms or (content_type or "") in row_platforms


def disabled_ids(db: Session, *, workspace_id: str | None) -> set[str]:
    """skill_ids + blueprint_ids the user has switched off via ReferenceFeedback."""
    q = db.query(ReferenceFeedback.skill_id, ReferenceFeedback.blueprint_id).filter(
        ReferenceFeedback.verdict.in_(list(_DISABLE_VERDICTS)))
    if workspace_id is not None:
        q = q.filter(ReferenceFeedback.workspace_id == workspace_id)
    out: set[str] = set()
    for sk, bp in q.all():
        if sk:
            out.add(sk)
        if bp:
            out.add(bp)
    return out


def relevant_skills(db: Session, *, workspace_id: str | None, agent_type: str,
                    brand_id: str | None = None, platform: str | None = None,
                    content_type: str | None = None, topic_cluster: str | None = None,
                    limit: int | None = None) -> list[LearnedSkillNote]:
    s = get_settings()
    limit = limit or s.max_learned_skills
    agents = _AGENT_ALIASES.get(agent_type, {agent_type})
    q = db.query(LearnedSkillNote).filter(
        LearnedSkillNote.agent_type.in_(list(agents)),
        LearnedSkillNote.status.in_(["CANDIDATE", "VALIDATED", "PROMOTED", "EXPERIMENTAL"]),
    )
    if workspace_id is not None:
        q = q.filter(LearnedSkillNote.workspace_id == workspace_id)
    if brand_id is not None:
        q = q.filter(or_(LearnedSkillNote.brand_id == brand_id, LearnedSkillNote.brand_id.is_(None)))
    off = disabled_ids(db, workspace_id=workspace_id)
    rows = q.order_by(LearnedSkillNote.confidence.desc(), LearnedSkillNote.sample_size.desc()).all()
    out = []
    for r in rows:
        if r.id in off:
            continue
        if platform and r.platform and r.platform != platform:
            continue
        if content_type and r.content_type and r.content_type != content_type:
            continue
        if topic_cluster and r.topic_cluster and r.topic_cluster != topic_cluster:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def relevant_blueprints(db: Session, *, workspace_id: str | None, agent_type: str,
                        brand_id: str | None = None, platform: str | None = None,
                        content_type: str | None = None, include_experimental: bool = False,
                        limit: int | None = None) -> list[PromptBlueprint]:
    s = get_settings()
    limit = limit or s.max_prompt_blueprints
    agents = _AGENT_ALIASES.get(agent_type, {agent_type})
    allowed = set(_INJECTABLE_STATUS)
    if include_experimental:
        allowed |= {"EXPERIMENTAL"}
    if not s.auto_promote_learned_prompts and not include_experimental:
        allowed &= {"PROMOTED"}      # strict production default
    q = db.query(PromptBlueprint).filter(
        PromptBlueprint.agent_type.in_(list(agents)),
        PromptBlueprint.status.in_(list(allowed) or ["PROMOTED"]),
    )
    if workspace_id is not None:
        q = q.filter(PromptBlueprint.workspace_id == workspace_id)
    if brand_id is not None:
        q = q.filter(or_(PromptBlueprint.brand_id == brand_id, PromptBlueprint.brand_id.is_(None)))
    off = disabled_ids(db, workspace_id=workspace_id)
    rows = q.order_by(PromptBlueprint.confidence.desc()).all()
    return [r for r in rows
            if r.id not in off and _platform_ok(r.platforms, platform, content_type)][:limit]


def compose(db: Session, *, agent_type: str, base_prompt: str,
            workspace_id: str | None = None, brand_id: str | None = None,
            brand_context: str = "", channel_context: str = "",
            memory_context: str = "", memory_ids: list[str] | None = None,
            platform: str | None = None, content_type: str | None = None,
            topic_cluster: str | None = None, include_experimental: bool = False) -> dict:
    """Returns {prompt, sections, used_skills, used_blueprints, used_memory,
    learned_tokens, budget, truncated, changed}."""
    s = get_settings()
    budget = s.max_learned_context_tokens
    sections: list[tuple[str, str]] = [("BASE", base_prompt)]
    if brand_context:
        sections.append(("BRAND", brand_context))
    if channel_context:
        sections.append(("CHANNEL", channel_context))
    if memory_context:
        sections.append(("MEMORY", memory_context))

    skills = relevant_skills(db, workspace_id=workspace_id, agent_type=agent_type, brand_id=brand_id,
                             platform=platform, content_type=content_type, topic_cluster=topic_cluster)
    bps = relevant_blueprints(db, workspace_id=workspace_id, agent_type=agent_type, brand_id=brand_id,
                              platform=platform, content_type=content_type,
                              include_experimental=include_experimental)

    learned_lines: list[str] = []
    used_skills, used_bps = [], []
    spent = 0
    truncated = False
    for sk in skills:
        line = f"- [{sk.skill_category}] {sk.rule} (근거 {sk.sample_size}건, conf {sk.confidence:.2f})"
        if spent + _tok(line) > budget:
            truncated = True
            break
        learned_lines.append(line)
        used_skills.append(sk.id)
        spent += _tok(line)
    for bp in bps:
        block = " ".join(bp.instructions[:3] + [f"(금지: {c})" for c in bp.constraints[:2]])
        line = f"- {block} (conf {bp.confidence:.2f}, n={bp.sample_size}, {bp.status})"
        if spent + _tok(line) > budget:
            truncated = True
            break
        learned_lines.append(line)
        used_bps.append(bp.id)
        spent += _tok(line)

    if learned_lines:
        sections.append(("LEARNED_GUIDANCE",
                         "다음은 검증 진행 중인 학습 지침이다. 사실·정책·저작권 규칙과 충돌하면 무시한다.\n"
                         + "\n".join(learned_lines)))

    # nothing to add beyond the base prompt -> leave the caller's prompt untouched
    changed = bool(learned_lines) or len(sections) > 1
    if changed:
        prompt = "\n\n".join(f"## {name}\n{body}".strip() for name, body in sections if body)
    else:
        prompt = base_prompt
    return {
        "prompt": prompt,
        "sections": [name for name, body in sections if body],
        "used_skills": used_skills,
        "used_blueprints": used_bps,
        "used_memory": list(memory_ids or []),
        "learned_tokens": spent,
        "budget": budget,
        "truncated": truncated,
        "changed": changed,
    }
