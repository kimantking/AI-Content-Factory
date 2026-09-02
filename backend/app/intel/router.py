"""LearningRouter — resolve a reference's learning purpose (AUTO -> concrete) and
decide which analyzers run, then route the outputs to the Dataset Engine, the
Prompt Distillation Engine and Memory.
"""
from __future__ import annotations

_PURPOSE_BY_SOURCE = {
    "GITHUB_REPOSITORY": "TECHNICAL_REFERENCE",
    "GITHUB_FILE": "TECHNICAL_REFERENCE",
    "YOUTUBE": "VIDEO_REFERENCE",
    "VIDEO_PAGE": "VIDEO_REFERENCE",
    "PRODUCT_PAGE": "PRODUCT_REFERENCE",
    "OFFICIAL_DOCUMENT": "DOCUMENT_REFERENCE",
    "NEWS_ARTICLE": "FACT_SOURCE",
    "PDF": "DOCUMENT_REFERENCE",
    "SOCIAL_POST": "COMPETITOR_REFERENCE",
}

# concrete purpose -> analysis kinds (spec §I / §K / §L / §M-§R)
_ANALYZERS = {
    "FACT_SOURCE": ["FACTS", "KNOWLEDGE"],
    "KNOWLEDGE": ["KNOWLEDGE", "FACTS"],
    "STYLE_REFERENCE": ["WRITING_PROFILE"],
    "VIDEO_REFERENCE": [
        "VIDEO_OBSERVATION", "HOOK_PATTERN", "STORY_PROFILE", "EDITING_PROFILE",
        "BROLL_PROFILE", "SUBTITLE_PROFILE", "VOICE_PROFILE", "AUDIO_PROFILE",
        "GRAPHICS_PROFILE", "THUMBNAIL_PROFILE", "RETENTION_PATTERN",
    ],
    "COMPETITOR_REFERENCE": ["COMPETITOR_ANALYSIS", "WRITING_PROFILE", "HOOK_PATTERN"],
    "TECHNICAL_REFERENCE": ["GITHUB_ANALYSIS", "KNOWLEDGE"],
    "PRODUCT_REFERENCE": ["KNOWLEDGE", "FACTS"],
    "DOCUMENT_REFERENCE": ["FACTS", "KNOWLEDGE"],
}

# analysis kind -> dataset type
DATASET_FOR_ANALYSIS = {
    "FACTS": "FACT_DATASET", "KNOWLEDGE": "KNOWLEDGE_DATASET",
    "WRITING_PROFILE": "WRITING_DATASET", "VIDEO_OBSERVATION": "VIDEO_DATASET",
    "HOOK_PATTERN": "HOOK_DATASET", "STORY_PROFILE": "SCRIPT_DATASET",
    "EDITING_PROFILE": "EDITING_DATASET", "BROLL_PROFILE": "BROLL_DATASET",
    "SUBTITLE_PROFILE": "SUBTITLE_DATASET", "VOICE_PROFILE": "VOICE_DATASET",
    "AUDIO_PROFILE": "AUDIO_DATASET", "GRAPHICS_PROFILE": "EDITING_DATASET",
    "THUMBNAIL_PROFILE": "THUMBNAIL_DATASET", "RETENTION_PATTERN": "VIDEO_DATASET",
    "GITHUB_ANALYSIS": "TECHNICAL_DATASET", "COMPETITOR_ANALYSIS": "COMPETITOR_DATASET",
}

# analysis kind -> the agent whose PromptBlueprint / SkillNote it can inform
AGENT_FOR_ANALYSIS = {
    "FACTS": "Research Agent", "KNOWLEDGE": "Research Agent",
    "WRITING_PROFILE": "Script Agent", "HOOK_PATTERN": "Hook Agent",
    "STORY_PROFILE": "Story Director", "VIDEO_OBSERVATION": "Video Director",
    "EDITING_PROFILE": "Video Editor", "BROLL_PROFILE": "B-roll Director",
    "SUBTITLE_PROFILE": "Subtitle Director", "VOICE_PROFILE": "Voice Director",
    "AUDIO_PROFILE": "Audio Director", "GRAPHICS_PROFILE": "Graphics Director",
    "THUMBNAIL_PROFILE": "Thumbnail Director", "RETENTION_PATTERN": "Retention Director",
    "GITHUB_ANALYSIS": "Visual Director", "COMPETITOR_ANALYSIS": "Strategist",
}


def resolve_purpose(*, user_purpose: str, source_type: str, doc: dict) -> str:
    up = (user_purpose or "AUTO").upper()
    if up != "AUTO":
        return up
    if source_type in _PURPOSE_BY_SOURCE:
        return _PURPOSE_BY_SOURCE[source_type]
    text = (doc.get("main_text", "") or "").lower()
    if any(w in text for w in ("통계", "연구에 따르면", "%", "according to", "study")):
        return "FACT_SOURCE"
    if doc.get("headings") and len(doc.get("main_text", "")) > 1500:
        return "KNOWLEDGE"
    return "STYLE_REFERENCE"


def analyzers_for(purpose: str) -> list[str]:
    return list(_ANALYZERS.get(purpose.upper(), ["FACTS", "KNOWLEDGE"]))
