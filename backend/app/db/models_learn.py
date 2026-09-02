"""Cross-Phase Intelligence Upgrade — URL Learning / Reference Dataset / Prompt
Distillation / Agent Skill Learning / Platform Selection.

Additive only. Registered on the shared Base via app.db.models. Reuses Research /
Fact Check / Memory / Learning / Video Studio / Governance / Analytics — no new
runtime architecture.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models import _now, _uuid

# ----- vocabularies ------------------------------------------------------ #

EXECUTION_MODE = ("CREATE_ONLY", "CREATE_AND_LEARN", "LEARN_ONLY", "REFERENCE_ONLY")

URL_SOURCE_TYPE = (
    "WEB_PAGE", "NEWS_ARTICLE", "BLOG", "OFFICIAL_DOCUMENT", "PDF",
    "GITHUB_REPOSITORY", "GITHUB_FILE", "YOUTUBE", "VIDEO_PAGE", "PRODUCT_PAGE",
    "SOCIAL_POST", "UNKNOWN",
)
SUPPORT_LEVEL = ("SUPPORTED", "LIMITED", "UNSUPPORTED", "AUTH_REQUIRED")

LEARNING_PURPOSE = (
    "AUTO", "FACT_SOURCE", "KNOWLEDGE", "STYLE_REFERENCE", "VIDEO_REFERENCE",
    "COMPETITOR_REFERENCE", "TECHNICAL_REFERENCE", "PRODUCT_REFERENCE",
    "DOCUMENT_REFERENCE",
)
LEARNING_SCOPE = ("THIS_RUN", "THIS_CAMPAIGN", "CHANNEL", "BRAND", "WORKSPACE")

REFERENCE_STATUS = (
    "PENDING", "FETCHING", "FETCH_FAILED", "BLOCKED", "EXTRACTED", "ANALYZING",
    "READY", "LOW_VALUE", "DUPLICATE", "REMOVED",
)

ANALYSIS_KIND = (
    "FACTS", "KNOWLEDGE", "WRITING_PROFILE", "VIDEO_OBSERVATION", "HOOK_PATTERN",
    "STORY_PROFILE", "EDITING_PROFILE", "BROLL_PROFILE", "SUBTITLE_PROFILE",
    "VOICE_PROFILE", "AUDIO_PROFILE", "GRAPHICS_PROFILE", "THUMBNAIL_PROFILE",
    "RETENTION_PATTERN", "GITHUB_ANALYSIS", "COMPETITOR_ANALYSIS", "QUALITY",
)

DATASET_TYPE = (
    "FACT_DATASET", "KNOWLEDGE_DATASET", "WRITING_DATASET", "HOOK_DATASET",
    "SCRIPT_DATASET", "VIDEO_DATASET", "EDITING_DATASET", "BROLL_DATASET",
    "VOICE_DATASET", "AUDIO_DATASET", "SUBTITLE_DATASET", "THUMBNAIL_DATASET",
    "PLATFORM_DATASET", "COMPETITOR_DATASET", "TECHNICAL_DATASET",
)

BLUEPRINT_STATUS = (
    "OBSERVED", "EXPERIMENTAL", "CANDIDATE", "VALIDATED", "PROMOTED",
    "DEPRECATED", "REJECTED",
)

EVIDENCE_TYPE = (
    "EXTERNAL_REFERENCE", "INTERNAL_CONTENT", "CONTROLLED_EXPERIMENT",
    "USER_FEEDBACK", "EXPERT_RULE",
)

PLATFORM_MODE = ("DISABLED", "GENERATE_ONLY", "GENERATE_AND_PUBLISH")


# ===================================================================== #
#  URL Learning
# ===================================================================== #

class ReferenceSource(Base):
    __tablename__ = "reference_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), index=True)
    learning_job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    collection_id: Mapped[str | None] = mapped_column(String(36), index=True)

    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text, default="")
    url_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    source_type: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    support_level: Mapped[str] = mapped_column(String(16), default="SUPPORTED")
    purpose: Mapped[str] = mapped_column(String(28), default="AUTO")
    resolved_purpose: Mapped[str] = mapped_column(String(28), default="AUTO")
    scope: Mapped[str] = mapped_column(String(16), default="THIS_CAMPAIGN")
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)

    title: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(200), default="")
    publisher: Mapped[str] = mapped_column(String(200), default="")
    published_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at_src: Mapped[str] = mapped_column(String(40), default="")
    language: Mapped[str] = mapped_column(String(12), default="")

    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    text_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    trust_score: Mapped[float] = mapped_column(Float, default=0.0)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0)
    originality_score: Mapped[float] = mapped_column(Float, default=0.0)
    noise_score: Mapped[float] = mapped_column(Float, default=0.0)
    learning_weight: Mapped[float] = mapped_column(Float, default=1.0)

    rights_status: Mapped[str] = mapped_column(String(28), default="RESEARCH_REFERENCE")
    injection_flag: Mapped[bool] = mapped_column(default=False)
    injection_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    fetch_adapter: Mapped[str] = mapped_column(String(24), default="http")
    topic_cluster: Mapped[str] = mapped_column(String(64), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now)


class ReferenceChunk(Base):
    __tablename__ = "reference_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    reference_id: Mapped[str] = mapped_column(
        ForeignKey("reference_sources.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    heading: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[float] = mapped_column(Float, default=0.0)   # 0..1 through the doc
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    sim_vector: Mapped[list] = mapped_column(JSON, default=list)
    text: Mapped[str] = mapped_column(Text, default="")


class ReferenceAnalysis(Base):
    __tablename__ = "reference_analysis"
    __table_args__ = (UniqueConstraint("reference_id", "analysis_kind", name="uq_ref_analysis_kind"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    reference_id: Mapped[str] = mapped_column(
        ForeignKey("reference_sources.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), index=True)
    analysis_kind: Mapped[str] = mapped_column(String(28), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)       # the extracted structure
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    unknown_fields: Mapped[list] = mapped_column(JSON, default=list)
    analyzer_version: Mapped[str] = mapped_column(String(24), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearningJob(Base):
    __tablename__ = "learning_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), index=True)
    collection_id: Mapped[str | None] = mapped_column(String(36), index=True)

    execution_mode: Mapped[str] = mapped_column(String(20), default="LEARN_ONLY")
    scope: Mapped[str] = mapped_column(String(16), default="THIS_CAMPAIGN")
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)

    total_urls: Mapped[int] = mapped_column(Integer, default=0)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    ready: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    low_value: Mapped[int] = mapped_column(Integer, default=0)
    datasets_written: Mapped[int] = mapped_column(Integer, default=0)
    blueprints_created: Mapped[int] = mapped_column(Integer, default=0)
    skills_created: Mapped[int] = mapped_column(Integer, default=0)

    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LearningCollection(Base):
    __tablename__ = "learning_collections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    default_purpose: Mapped[str] = mapped_column(String(28), default="AUTO")
    default_scope: Mapped[str] = mapped_column(String(16), default="CHANNEL")
    reference_count: Mapped[int] = mapped_column(Integer, default=0)
    watchlist: Mapped[dict] = mapped_column(JSON, default=dict)   # opt-in RSS / API sources
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ===================================================================== #
#  Dataset Engine
# ===================================================================== #

class DatasetRecord(Base):
    __tablename__ = "dataset_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), index=True)
    reference_id: Mapped[str | None] = mapped_column(
        ForeignKey("reference_sources.id", ondelete="SET NULL"), index=True)
    dataset_type: Mapped[str] = mapped_column(String(24), index=True)

    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    trust_score: Mapped[float] = mapped_column(Float, default=0.0)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0)
    originality_score: Mapped[float] = mapped_column(Float, default=0.0)
    learning_weight: Mapped[float] = mapped_column(Float, default=1.0)

    rights_status: Mapped[str] = mapped_column(String(28), default="RESEARCH_REFERENCE")
    language: Mapped[str] = mapped_column(String(12), default="")
    topic_cluster: Mapped[str] = mapped_column(String(64), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    curator_flags: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ===================================================================== #
#  Prompt Distillation
# ===================================================================== #

class PromptBlueprint(Base):
    __tablename__ = "prompt_blueprints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), index=True)

    agent_type: Mapped[str] = mapped_column(String(40), index=True)
    purpose: Mapped[str] = mapped_column(String(120), default="")
    instructions: Mapped[list] = mapped_column(JSON, default=list)
    constraints: Mapped[list] = mapped_column(JSON, default=list)
    positive_patterns: Mapped[list] = mapped_column(JSON, default=list)
    negative_patterns: Mapped[list] = mapped_column(JSON, default=list)
    platforms: Mapped[list] = mapped_column(JSON, default=list)
    content_types: Mapped[list] = mapped_column(JSON, default=list)
    topic_clusters: Mapped[list] = mapped_column(JSON, default=list)

    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    source_diversity: Mapped[float] = mapped_column(Float, default=0.0)
    consistency: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="OBSERVED", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    prev_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    experiment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now)


class PromptBlueprintEvidence(Base):
    __tablename__ = "prompt_blueprint_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    blueprint_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_blueprints.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    evidence_type: Mapped[str] = mapped_column(String(28), default="EXTERNAL_REFERENCE")
    reference_id: Mapped[str | None] = mapped_column(String(36), index=True)
    dataset_record_id: Mapped[str | None] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(36), index=True)
    observation: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    metric_delta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ===================================================================== #
#  Agent Skill Learning
# ===================================================================== #

class LearnedSkillNote(Base):
    __tablename__ = "learned_skill_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), index=True)

    agent_type: Mapped[str] = mapped_column(String(40), index=True)
    skill_category: Mapped[str] = mapped_column(String(40), default="")
    rule: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    platform: Mapped[str] = mapped_column(String(24), default="")
    content_type: Mapped[str] = mapped_column(String(24), default="")
    topic_cluster: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="OBSERVED", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now)


class CreativeRecipe(Base):
    __tablename__ = "creative_recipes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    platform: Mapped[str] = mapped_column(String(24), default="")
    content_type: Mapped[str] = mapped_column(String(24), default="")
    hook_pattern: Mapped[dict] = mapped_column(JSON, default=dict)
    story_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    editing_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    broll_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    voice_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    subtitle_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    graphics_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    audio_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    thumbnail_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="OBSERVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReferenceFeedback(Base):
    __tablename__ = "reference_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), index=True)
    blueprint_id: Mapped[str | None] = mapped_column(String(36), index=True)
    skill_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="")
    verdict: Mapped[str] = mapped_column(String(24), default="")   # USEFUL|NOT_USEFUL|WRONG|BLOCK
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ===================================================================== #
#  Platform Selection
# ===================================================================== #

class CampaignPlatformSelection(Base):
    __tablename__ = "campaign_platform_selections"
    __table_args__ = (
        UniqueConstraint("campaign_id", "platform", "content_type", name="uq_campaign_platform_ct"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    content_type: Mapped[str] = mapped_column(String(24), default="")
    mode: Mapped[str] = mapped_column(String(24), default="DISABLED")
    user_explicit: Mapped[bool] = mapped_column(default=True)   # hard rule vs inherited default
    source: Mapped[str] = mapped_column(String(24), default="USER")  # USER|PRESET|CHANNEL|BRAND|WORKSPACE
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now)


class PlatformPreset(Base):
    __tablename__ = "platform_presets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120))
    builtin: Mapped[bool] = mapped_column(default=False)
    selection: Mapped[dict] = mapped_column(JSON, default=dict)   # {platform: {content_type: mode}}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ----- migration helpers ---------------------------------------------- #

LEARN_TABLES = [
    "learning_collections", "learning_jobs", "reference_sources", "reference_chunks",
    "reference_analysis", "dataset_records", "prompt_blueprints",
    "prompt_blueprint_evidence", "learned_skill_notes", "creative_recipes",
    "reference_feedback", "campaign_platform_selections", "platform_presets",
]

LEARN_ALTERS = [
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(20)",
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS platform_selection_locked BOOLEAN DEFAULT FALSE",
    "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS platform_selection_mode VARCHAR(24)",
    "CREATE INDEX IF NOT EXISTS ix_reference_dedup ON reference_sources (workspace_id, content_hash)",
    "CREATE INDEX IF NOT EXISTS ix_dataset_lookup ON dataset_records (workspace_id, dataset_type, active)",
    "CREATE INDEX IF NOT EXISTS ix_blueprint_lookup ON prompt_blueprints (workspace_id, agent_type, status)",
    "CREATE INDEX IF NOT EXISTS ix_skill_lookup ON learned_skill_notes (workspace_id, agent_type, status)",
    "CREATE INDEX IF NOT EXISTS ix_platform_sel ON campaign_platform_selections (campaign_id, platform)",
]
