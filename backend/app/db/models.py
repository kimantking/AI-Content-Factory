from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    audience_goal: Mapped[str] = mapped_column(String(32), default="BALANCED")
    platforms: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="WAITING", index=True)
    current_step: Mapped[str | None] = mapped_column(String(32), nullable=True)
    knowledge_pack: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fact_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Phase 6 tenant scope (NULLABLE — legacy rows stay NULL)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # Cross-Phase Intelligence Upgrade (NULLABLE; see models_learn.LEARN_ALTERS / 0009)
    execution_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    platform_selection_locked: Mapped[bool | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now
    )

    sources: Mapped[list["ResearchSource"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    facts: Mapped[list["VerifiedFact"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    strategies: Mapped[list["Strategy"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    hooks: Mapped[list["Hook"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    scripts: Mapped[list["Script"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    cost_logs: Mapped[list["CostLog"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    errors: Mapped[list["ErrorLog"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class ResearchSource(Base):
    __tablename__ = "research_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    snippet: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    campaign: Mapped[Campaign] = relationship(back_populates="sources")


class VerifiedFact(Base):
    __tablename__ = "verified_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    fact: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24))  # VERIFIED | PARTIALLY_VERIFIED | UNVERIFIED | CONTRADICTED
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text, default="")

    campaign: Mapped[Campaign] = relationship(back_populates="facts")


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    angle: Mapped[str] = mapped_column(Text)
    key_message: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(String(64), default="")
    target_emotion: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    campaign: Mapped[Campaign] = relationship(back_populates="strategies")


class Hook(Base):
    __tablename__ = "hooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    style: Mapped[str] = mapped_column(String(64), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    rank: Mapped[int] = mapped_column(Integer, default=0)

    campaign: Mapped[Campaign] = relationship(back_populates="hooks")


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="MASTER")
    body: Mapped[str] = mapped_column(Text)
    draft_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    qa_passed: Mapped[bool] = mapped_column(default=False)
    qa_report: Mapped[dict] = mapped_column(JSON, default=dict)
    cta_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    ai_slop_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    naturalness: Mapped[dict] = mapped_column(JSON, default=dict)

    campaign: Mapped[Campaign] = relationship(back_populates="scripts")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")  # RUNNING|SUCCESS|RETRY|FAILED
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    campaign: Mapped[Campaign] = relationship(back_populates="agent_runs")


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(16))
    content_hash: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CostLog(Base):
    __tablename__ = "cost_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16), default="LLM")  # LLM|SEARCH|IMAGE|VIDEO|TTS|STOCK
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    campaign: Mapped[Campaign] = relationship(back_populates="cost_logs")


class ErrorLog(Base):
    __tablename__ = "errors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scope: Mapped[str] = mapped_column(String(32), default="pipeline")
    error_type: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    campaign: Mapped[Campaign] = relationship(back_populates="errors")


# --------------------------------------------------------------------------- #
# Phase 1-B — Media Production
# --------------------------------------------------------------------------- #

class PlatformContent(Base):
    __tablename__ = "platform_contents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    content_type: Mapped[str] = mapped_column(String(24))
    hook: Mapped[str] = mapped_column(Text, default="")
    script: Mapped[str] = mapped_column(Text, default="")
    cta: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list] = mapped_column(JSON, default=list)
    target_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aspect_ratio: Mapped[str] = mapped_column(String(12), default="9:16")
    visual_style: Mapped[str] = mapped_column(String(48), default="")
    subtitle_style: Mapped[str] = mapped_column(String(24), default="")
    voice_style: Mapped[str] = mapped_column(String(24), default="")
    music_style: Mapped[str] = mapped_column(String(24), default="")
    thumbnail_required: Mapped[bool] = mapped_column(default=False)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Phase 7 — content governance (additive; see models_gov.GOV_ALTERS / 0008)
    governance_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    governance_decision: Mapped[str | None] = mapped_column(String(28), nullable=True)

    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="content", cascade="all, delete-orphan", order_by="Scene.scene_order"
    )


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("platform_contents.id", ondelete="CASCADE"), index=True)
    scene_order: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[float] = mapped_column(Float, default=0.0)
    end_time: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_duration: Mapped[float] = mapped_column(Float, default=0.0)
    narration: Mapped[str] = mapped_column(Text, default="")
    visual_type: Mapped[str] = mapped_column(String(24), default="AI_IMAGE")
    visual_description: Mapped[str] = mapped_column(Text, default="")
    visual_prompt: Mapped[dict] = mapped_column(JSON, default=dict)
    negative_prompt: Mapped[str] = mapped_column(Text, default="")
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    camera_motion: Mapped[str] = mapped_column(String(64), default="SLOW_ZOOM_IN")
    # Stores a human-readable fallback/creative-direction reason, not an enum.
    motion_effect: Mapped[str] = mapped_column(Text, default="")
    transition: Mapped[str] = mapped_column(String(16), default="CUT")
    subtitle_text: Mapped[str] = mapped_column(Text, default="")
    highlight_words: Mapped[list] = mapped_column(JSON, default=list)
    sound_effect: Mapped[str] = mapped_column(String(32), default="")
    music_energy: Mapped[str] = mapped_column(String(12), default="mid")
    consistency_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    generation_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    generation_status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    edit_decision: Mapped[dict] = mapped_column(JSON, default=dict)
    asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )

    content: Mapped[PlatformContent] = relationship(back_populates="scenes")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    scene_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    asset_type: Mapped[str] = mapped_column(String(24), index=True)  # image|video|audio|subtitle|render|thumbnail|chart|carousel
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    provider_mode: Mapped[str] = mapped_column(String(12), default="MOCK")  # REAL|MOCK|DISABLED|ERROR
    prompt: Mapped[str] = mapped_column(Text, default="")
    hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    storage_path: Mapped[str] = mapped_column(Text, default="")
    mime_type: Mapped[str] = mapped_column(String(48), default="")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="SUCCESS", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MediaTask(Base):
    __tablename__ = "media_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    scene_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)   # image|video|audio|render|thumbnail|...
    queue: Mapped[str] = mapped_column(String(24), default="media")
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_mode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cost: Mapped[float] = mapped_column(Float, default=0.0)
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --------------------------------------------------------------------------- #
# Phase 2 — Multi-Platform Publishing
# --------------------------------------------------------------------------- #

class PlatformAccount(Base):
    __tablename__ = "platform_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(48), nullable=True)  # e.g. BUSINESS / CREATOR / PAGE / PERSONAL
    connection_status: Mapped[str] = mapped_column(String(24), default="DISCONNECTED", index=True)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    integration_status: Mapped[str] = mapped_column(String(32), default="MOCK_TESTED")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now
    )


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    state: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(32))
    redirect_uri: Mapped[str] = mapped_column(Text)
    code_verifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    consumed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    platform_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("platform_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(32), index=True)
    content_type: Mapped[str] = mapped_column(String(24), default="")

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    timezone: Mapped[str] = mapped_column(String(48), default="Asia/Seoul")

    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list] = mapped_column(JSON, default=list)
    media_asset_ids: Mapped[list] = mapped_column(JSON, default=list)
    thumbnail_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    privacy: Mapped[str] = mapped_column(String(24), default="PRIVATE")
    platform_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_generated: Mapped[bool] = mapped_column(default=True)
    sponsored: Mapped[bool] = mapped_column(default=False)

    approval_status: Mapped[str] = mapped_column(String(24), default="PENDING")  # PENDING/APPROVED/REJECTED
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_mode: Mapped[str] = mapped_column(String(16), default="MANUAL")

    status: Mapped[str] = mapped_column(String(28), default="DRAFT", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    idempotency_key: Mapped[str] = mapped_column(String(80), index=True, default="")

    remote_post_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remote_container_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remote_publish_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    dry_run: Mapped[bool] = mapped_column(default=False)
    last_error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dead_lettered: Mapped[bool] = mapped_column(default=False)

    # Phase 7 — content governance (additive; see models_gov.GOV_ALTERS / 0008)
    governance_decision: Mapped[str | None] = mapped_column(String(28), nullable=True)
    disclosure_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Cross-Phase Intelligence Upgrade — platform selection at job-creation time
    platform_selection_mode: Mapped[str | None] = mapped_column(String(24), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now
    )


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    publish_job_id: Mapped[str] = mapped_column(ForeignKey("publish_jobs.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    platform_account_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    remote_post_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    remote_container_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remote_publish_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(28), default="PENDING", index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upload_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upload_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_mode: Mapped[str] = mapped_column(String(12), default="MOCK")
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now
    )


class PublicationEvent(Base):
    __tablename__ = "publication_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    publish_job_id: Mapped[str] = mapped_column(ForeignKey("publish_jobs.id", ondelete="CASCADE"), index=True)
    publication_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublishAudit(Base):
    __tablename__ = "publish_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    publish_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(128), default="system")
    action: Mapped[str] = mapped_column(String(48))
    run_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --------------------------------------------------------------------------- #
# Phase 3 — Analytics / Learning / Memory / Revenue
# --------------------------------------------------------------------------- #

class MetricDef(Base):
    __tablename__ = "metric_catalog"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    metric_id: Mapped[str] = mapped_column(String(80), index=True)      # platform:api_metric_name
    platform: Mapped[str] = mapped_column(String(32), index=True)
    api_metric_name: Mapped[str] = mapped_column(String(80))
    normalized_name: Mapped[str] = mapped_column(String(48), index=True)
    unit: Mapped[str] = mapped_column(String(24), default="count")
    content_types: Mapped[list] = mapped_column(JSON, default=list)
    availability: Mapped[str] = mapped_column(String(20), default="AVAILABLE")
    aggregation_type: Mapped[str] = mapped_column(String(16), default="cumulative")
    formula_version: Mapped[str] = mapped_column(String(12), default="v1")
    description: Mapped[str] = mapped_column(Text, default="")
    last_verified_at: Mapped[str] = mapped_column(String(16), default="")


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    publication_id: Mapped[str] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    platform_account_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    content_age_minutes: Mapped[int] = mapped_column(Integer, default=0)
    window_label: Mapped[str] = mapped_column(String(16), default="", index=True)

    # normalized metrics — None means genuinely unknown, never coerced to 0
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    impressions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reach: Mapped[int | None] = mapped_column(Integer, nullable=True)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    saves: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reposts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bookmarks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quotes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watch_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_watch_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_view_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    followers_gained: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subscribers_gained: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_visits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link_clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="KRW")

    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)     # RAW layer, never deleted
    metric_availability: Mapped[dict] = mapped_column(JSON, default=dict)  # normalized_name -> status
    data_source: Mapped[str] = mapped_column(String(20), default="PLATFORM_API")
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    collection_status: Mapped[str] = mapped_column(String(16), default="SUCCESS")  # SUCCESS|PARTIAL|FAILED|UNAVAILABLE
    anomaly_flags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalyticsJob(Base):
    __tablename__ = "analytics_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    publication_id: Mapped[str] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    window_label: Mapped[str] = mapped_column(String(16))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="SCHEDULED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentFeature(Base):
    __tablename__ = "content_features"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    content_id: Mapped[str] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    content_type: Mapped[str] = mapped_column(String(24), default="")
    topic: Mapped[str] = mapped_column(Text, default="")
    topic_cluster: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    topic_embedding: Mapped[list] = mapped_column(JSON, default=list)
    hook_text: Mapped[str] = mapped_column(Text, default="")
    hook_type: Mapped[str] = mapped_column(String(24), default="OTHER")
    hook_length: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(Text, default="")
    title_length: Mapped[int] = mapped_column(Integer, default=0)
    script_length: Mapped[int] = mapped_column(Integer, default=0)
    video_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    scene_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_scene_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    scene_duration_variance: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_video_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    ai_image_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    stock_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    motion_graphic_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    voice_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    voice_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    voice_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    voice_speed_variance: Mapped[float | None] = mapped_column(Float, nullable=True)
    voice_energy: Mapped[float | None] = mapped_column(Float, nullable=True)
    subtitle_style: Mapped[str | None] = mapped_column(String(24), nullable=True)
    subtitle_density: Mapped[float | None] = mapped_column(Float, nullable=True)
    subtitle_highlight_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    transition_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    camera_motion_diversity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_style: Mapped[str | None] = mapped_column(String(32), nullable=True)
    thumbnail_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cta_type: Mapped[str] = mapped_column(String(24), default="NONE")
    publish_weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publish_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_cost: Mapped[float] = mapped_column(Float, default=0.0)
    prompt_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    naturalness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_slop_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    visual_repetition_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    edit_repetition_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PerformanceScore(Base):
    __tablename__ = "performance_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    publication_id: Mapped[str] = mapped_column(String(36), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    content_type: Mapped[str] = mapped_column(String(24), default="")
    objective: Mapped[str] = mapped_column(String(16), default="BALANCED")
    objective_config_version: Mapped[str] = mapped_column(String(12), default="v1")
    score: Mapped[float] = mapped_column(Float, default=0.0)             # 0..100
    components: Mapped[dict] = mapped_column(JSON, default=dict)
    relative_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # vs baseline
    baseline_ref: Mapped[dict] = mapped_column(JSON, default=dict)
    is_outlier: Mapped[bool] = mapped_column(default=False)
    has_anomaly: Mapped[bool] = mapped_column(default=False)
    snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RevenueEntry(Base):
    __tablename__ = "revenue_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    publication_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(16), index=True)  # PLATFORM_API|AFFILIATE|SPONSOR|PRODUCT|MANUAL|ESTIMATE
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="KRW")
    is_estimate: Mapped[bool] = mapped_column(default=False)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CostAllocation(Base):
    __tablename__ = "cost_allocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    publication_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)  # LLM|IMAGE|VIDEO|TTS|STOCK|MUSIC|RENDER|STORAGE|PUBLISHING|INFRA
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    source_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)  # cost_logs id etc
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearningMemory(Base):
    __tablename__ = "learning_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    platform_account_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    memory_type: Mapped[str] = mapped_column(String(24), index=True)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    content_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    topic_cluster: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    statement: Mapped[str] = mapped_column(Text)
    dimension: Mapped[str | None] = mapped_column(String(32), nullable=True)   # e.g. hook_type / duration
    recommendation: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="EXPERIMENTAL", index=True)
    pinned: Mapped[bool] = mapped_column(default=False)
    hard_policy: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class ContentRecipe(Base):
    __tablename__ = "content_recipes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    content_type: Mapped[str] = mapped_column(String(24), default="")
    topic_cluster: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    objective: Mapped[str] = mapped_column(String(16), default="BALANCED")
    recipe: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="EXPERIMENTAL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now
    )


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    hypothesis: Mapped[str] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(String(32))
    content_type: Mapped[str] = mapped_column(String(24), default="")
    variable: Mapped[str] = mapped_column(String(24), index=True)
    control: Mapped[dict] = mapped_column(JSON, default=dict)
    variant: Mapped[dict] = mapped_column(JSON, default=dict)
    primary_metric: Mapped[str] = mapped_column(String(32), default="performance_score")
    minimum_sample: Mapped[int] = mapped_column(Integer, default=10)
    design: Mapped[str] = mapped_column(String(24), default="SEQUENTIAL_EXPERIMENT")
    status: Mapped[str] = mapped_column(String(16), default="RUNNING", index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class ExperimentResult(Base):
    __tablename__ = "experiment_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    arm: Mapped[str] = mapped_column(String(12))     # control | variant
    content_id: Mapped[str] = mapped_column(String(36))
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearningRun(Base):
    __tablename__ = "daily_learning_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_date: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # YYYY-MM-DD, idempotent
    snapshots_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    memories_touched: Mapped[int] = mapped_column(Integer, default=0)
    recipes_touched: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="SUCCESS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PeriodReport(Base):
    __tablename__ = "period_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    period_type: Mapped[str] = mapped_column(String(10), index=True)   # weekly | monthly
    period_key: Mapped[str] = mapped_column(String(16), index=True)    # 2026-W35 / 2026-08
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --------------------------------------------------------------------------- #
# Phase 4 — Trend Intelligence / Opportunity Engine / AUTOPILOT
# --------------------------------------------------------------------------- #

class TrendSource(Base):
    __tablename__ = "trend_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(96))
    source_type: Mapped[str] = mapped_column(String(20))   # OFFICIAL_API|APPROVED_API|PUBLIC_SEARCH|OWN_ANALYTICS|MANUAL|OPTIONAL
    provider: Mapped[str] = mapped_column(String(48))
    enabled: Mapped[bool] = mapped_column(default=True)
    auth_status: Mapped[str] = mapped_column(String(20), default="UNAVAILABLE")  # AVAILABLE|AUTH_REQUIRED|APPROVAL_REQUIRED|LIMITED|DISABLED|UNAVAILABLE
    country: Mapped[str] = mapped_column(String(8), default="KR")
    language: Mapped[str] = mapped_column(String(8), default="ko")
    freshness: Mapped[str] = mapped_column(String(16), default="unknown")
    reliability: Mapped[float] = mapped_column(Float, default=0.5)
    cost: Mapped[str] = mapped_column(String(24), default="free")
    rate_limit: Mapped[str] = mapped_column(String(48), default="")
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health: Mapped[str] = mapped_column(String(12), default="UNKNOWN")
    value_score: Mapped[float] = mapped_column(Float, default=0.5)   # learned reliability of picks
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class RawTrendEvent(Base):
    __tablename__ = "raw_trend_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(48), index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    raw_topic: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str] = mapped_column(String(8), default="KR")
    language: Mapped[str] = mapped_column(String(8), default="ko")
    engagement_signals: Mapped[dict] = mapped_column(JSON, default=dict)
    source_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    reliability: Mapped[str] = mapped_column(String(16), default="unknown")
    dedup_key: Mapped[str] = mapped_column(String(64), index=True, default="")
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class TopicCandidate(Base):
    __tablename__ = "topic_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    topic: Mapped[str] = mapped_column(Text)
    angle: Mapped[str] = mapped_column(Text, default="")
    topic_cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_audience: Mapped[str] = mapped_column(String(96), default="")
    country: Mapped[str] = mapped_column(String(8), default="KR")
    language: Mapped[str] = mapped_column(String(8), default="ko")
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trend_type: Mapped[str] = mapped_column(String(16), default="NORMAL_TREND")

    # sub-scores (0..100 or null)
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    velocity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    acceleration_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    freshness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    historical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    audience_fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    competition_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    saturation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    originality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fact_availability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    production_cost_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    production_difficulty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    natural_content_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fatigue_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(12), default="LOW")
    risk_categories: Mapped[list] = mapped_column(JSON, default=list)

    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    dedup_status: Mapped[str] = mapped_column(String(12), default="NEW")   # NEW|SIMILAR|DUPLICATE|NEW_ANGLE
    platform_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    opportunity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    opportunity_formula_version: Mapped[str] = mapped_column(String(24), default="opportunity_formula_v1")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    portfolio_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="CANDIDATE", index=True)  # CANDIDATE|PRESCORED|SCORED|SELECTED|REJECTED|BLOCKED|PRODUCING|SCHEDULED|CANCELLED
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    stage: Mapped[int] = mapped_column(Integer, default=1)


class AutopilotRun(Base):
    __tablename__ = "autopilot_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mode: Mapped[str] = mapped_column(String(16))
    trigger: Mapped[str] = mapped_column(String(24), default="manual")   # manual|schedule|breakout
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    country: Mapped[str] = mapped_column(String(8), default="KR")
    language: Mapped[str] = mapped_column(String(8), default="ko")
    objective: Mapped[str] = mapped_column(String(16), default="BALANCED")
    config_version: Mapped[str] = mapped_column(String(24), default="v1")
    raw_candidates: Mapped[int] = mapped_column(Integer, default=0)
    final_candidates: Mapped[int] = mapped_column(Integer, default=0)
    selected_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cost: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING", index=True)  # RUNNING|SUCCESS|HOLD|PAUSED|STOPPED|FAILED
    pause_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage: Mapped[str] = mapped_column(String(24), default="scan")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class AutopilotDecision(Base):
    __tablename__ = "autopilot_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    decision_type: Mapped[str] = mapped_column(String(32), index=True)
    input_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    selected: Mapped[bool] = mapped_column(default=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    config_version: Mapped[str] = mapped_column(String(24), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AutopilotConfigVersion(Base):
    __tablename__ = "autopilot_config_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    version: Mapped[str] = mapped_column(String(24), index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    changed_by: Mapped[str] = mapped_column(String(64), default="user")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TopicRejection(Base):
    __tablename__ = "topic_rejections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    topic_cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    topic: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(12), default="ONCE")   # ONCE | PERMANENT
    reason: Mapped[str] = mapped_column(String(32), default="OTHER")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --------------------------------------------------------------------------- #
# Phase 5 — Production / Security / Backup / Monitoring
# --------------------------------------------------------------------------- #

class RuntimeSetting(Base):
    """DB-controlled operational flags. Persist across process restarts —
    EMERGENCY_STOP / SAFE_MODE / MAINTENANCE_MODE must NOT clear on restart."""
    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[str] = mapped_column(String(64), default="system")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now
    )


class ConfigChangeLog(Base):
    __tablename__ = "config_change_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    config_version: Mapped[str] = mapped_column(String(32), index=True)
    key: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[dict] = mapped_column(JSON, default=dict)
    new_value: Mapped[dict] = mapped_column(JSON, default=dict)
    changed_by: Mapped[str] = mapped_column(String(64), default="user")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkerRegistration(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)   # worker_id
    worker_type: Mapped[str] = mapped_column(String(24), index=True)
    hostname: Mapped[str] = mapped_column(String(128), default="")
    version: Mapped[str] = mapped_column(String(32), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    current_job: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="HEALTHY")  # HEALTHY|BUSY|DEGRADED|STALE|DEAD
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class JobLease(Base):
    """Generic lease so a crashed worker never leaves a job RUNNING forever."""
    __tablename__ = "job_leases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_kind: Mapped[str] = mapped_column(String(24), index=True)   # media|publish|analytics|autopilot|render
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    worker_id: Mapped[str] = mapped_column(String(64))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    released: Mapped[bool] = mapped_column(default=False, index=True)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)  # DONE|FAILED|STUCK|RECOVERED

    __table_args__ = (UniqueConstraint("job_kind", "job_id", "released", name="uq_active_lease"),)


class BackupManifest(Base):
    __tablename__ = "backup_manifests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(16), default="full")   # full | storage
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    app_version: Mapped[str] = mapped_column(String(32), default="")
    db_version: Mapped[str] = mapped_column(String(32), default="")
    migration_revision: Mapped[str] = mapped_column(String(48), default="")
    method: Mapped[str] = mapped_column(String(24), default="pg_dump")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), default="")
    storage_location: Mapped[str] = mapped_column(Text, default="")
    encryption: Mapped[str] = mapped_column(String(16), default="none")
    status: Mapped[str] = mapped_column(String(16), default="CREATED")  # CREATED|VERIFIED|RESTORE_TESTED|FAILED
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    restore_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class OpsAlert(Base):
    __tablename__ = "ops_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    severity: Mapped[str] = mapped_column(String(12), index=True)   # INFO|WARNING|HIGH|CRITICAL
    key: Mapped[str] = mapped_column(String(64), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="OPEN")  # OPEN|ACK|RESOLVED
    count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEntry(Base):
    """Append-only audit for sensitive actions. Application code never updates or
    deletes these rows."""
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    action: Mapped[str] = mapped_column(String(48), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeadLetter(Base):
    __tablename__ = "dead_letters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_kind: Mapped[str] = mapped_column(String(24), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str] = mapped_column(String(48))
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="OPEN")  # OPEN|RETRIED|CANCELLED|RESOLVED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now
    )

# Phase 6 multi-brand models (registered on the shared Base)
from app.db import models_mb as _mb  # noqa: E402,F401

# Phase 7 governance models
from app.db import models_gov as _gov  # noqa: E402,F401

# Cross-Phase Intelligence Upgrade — URL learning / dataset / prompt / skill / platform selection
from app.db import models_learn as _learn  # noqa: E402,F401

# Phase 8 — model router telemetry + performance memory
from app.db import models_p8 as _p8  # noqa: E402,F401

# Phase 11 — provider credential vault (encrypted API keys)
from app.db import models_p11 as _p11  # noqa: E402,F401
