from __future__ import annotations

from typing import Any, TypedDict


class PipelineState(TypedDict, total=False):
    # identity / input
    campaign_id: str
    topic: str
    audience_goal: str
    platforms: list[str]

    # research
    sources: list[dict[str, Any]]
    candidate_facts: list[dict[str, Any]]
    research_fix_count: int

    # fact check
    facts: list[dict[str, Any]]
    fact_score: float

    # knowledge pack (single source of truth)
    knowledge_pack: dict[str, Any]

    # downstream
    strategy: dict[str, Any]
    hooks: list[dict[str, Any]]
    chosen_hook: dict[str, Any]
    script: dict[str, Any]
    script_qa: dict[str, Any]

    # control
    status: str
    error: dict[str, Any] | None


def initial_state(campaign_id: str, topic: str, audience_goal: str, platforms: list[str]) -> PipelineState:
    return PipelineState(
        campaign_id=campaign_id,
        topic=topic,
        audience_goal=audience_goal,
        platforms=platforms,
        research_fix_count=0,
        status="RUNNING",
        error=None,
    )
