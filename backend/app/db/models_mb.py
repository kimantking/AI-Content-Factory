"""Phase 6 — Multi-Brand / Multi-Channel / Portfolio / Monetization models.

All additive. Kept in a separate module for clarity; imported by app.db.models
so they register on the shared Base. Tenant-scope columns on pre-existing tables
are added NULLABLE in migration 0007 (`_ALTERS`) so the existing suite is
unaffected — new code sets them, legacy rows stay NULL.
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

ROLES = ("OWNER", "ADMIN", "EDITOR", "PUBLISHER", "ANALYST", "VIEWER")
PORTFOLIO_OBJECTIVES = ("GROWTH", "REVENUE", "PROFIT", "DIVERSIFICATION", "BRAND", "BALANCED")
CHANNEL_LIFECYCLE = ("DRAFT", "WARMUP", "ACTIVE", "GROWTH", "MATURE", "DECLINING", "PAUSED", "ARCHIVED")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    api_key_hash: Mapped[str | None] = mapped_column(String(128), default=None, index=True)
    is_system_admin: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Seoul")
    default_language: Mapped[str] = mapped_column(String(8), default="ko")
    default_country: Mapped[str] = mapped_column(String(4), default="KR")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")  # ACTIVE|SUSPENDED|EMERGENCY_STOP
    daily_hard_budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_hard_budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    objective: Mapped[str] = mapped_column(String(16), default="BALANCED")
    min_exploration_budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=_now)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_ws_member"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Brand(Base):
    __tablename__ = "brands"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_brand_slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), default="")
    language: Mapped[str] = mapped_column(String(8), default="ko")
    country: Mapped[str] = mapped_column(String(4), default="KR")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    primary_objective: Mapped[str] = mapped_column(String(16), default="BALANCED")
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")  # ACTIVE|PAUSED|ARCHIVED
    daily_hard_budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_hard_budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    voice_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    visual_identity: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    disclosure_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=_now)


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(40))
    platform_account_id: Mapped[str | None] = mapped_column(String(36), default=None)
    channel_type: Mapped[str] = mapped_column(String(32), default="YOUTUBE_SHORTS")
    language: Mapped[str] = mapped_column(String(8), default="ko")
    country: Mapped[str] = mapped_column(String(4), default="KR")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    primary_objective: Mapped[str] = mapped_column(String(16), default="BALANCED")
    content_strategy: Mapped[dict] = mapped_column(JSON, default=dict)
    production_profile: Mapped[str] = mapped_column(String(16), default="STANDARD")
    autopilot_mode: Mapped[str] = mapped_column(String(16), default="OFF")
    daily_min_posts: Mapped[int] = mapped_column(Integer, default=0)
    daily_max_posts: Mapped[int] = mapped_column(Integer, default=2)
    daily_budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    lifecycle: Mapped[str] = mapped_column(String(12), default="DRAFT")
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")  # ACTIVE|PAUSED|ARCHIVED
    schedule: Mapped[dict] = mapped_column(JSON, default=dict)
    brand_safety: Mapped[dict] = mapped_column(JSON, default=dict)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=_now)


class ContentPillar(Base):
    __tablename__ = "content_pillars"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120))
    target_share: Mapped[float] = mapped_column(Float, default=0.25)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChannelHealthSnapshot(Base):
    __tablename__ = "channel_health_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    components: Mapped[dict] = mapped_column(JSON, default=dict)
    lifecycle: Mapped[str] = mapped_column(String(12), default="DRAFT")
    scale_status: Mapped[str] = mapped_column(String(20), default="NOT_ENOUGH_DATA")
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChannelOperatingPlan(Base):
    __tablename__ = "channel_operating_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    objective: Mapped[str] = mapped_column(String(16), default="BALANCED")
    channels: Mapped[dict] = mapped_column(JSON, default=dict)
    totals: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioDecision(Base):
    __tablename__ = "portfolio_decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), default=None, index=True)
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    applied: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BudgetAllocation(Base):
    __tablename__ = "budget_allocations"
    __table_args__ = (UniqueConstraint("scope", "scope_id", "period", name="uq_budget_alloc"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    scope: Mapped[str] = mapped_column(String(12))    # WORKSPACE|BRAND|CHANNEL
    scope_id: Mapped[str] = mapped_column(String(36), index=True)
    period: Mapped[str] = mapped_column(String(12), default="daily")
    hard_limit_usd: Mapped[float] = mapped_column(Float, default=0.0)
    soft_target_usd: Mapped[float] = mapped_column(Float, default=0.0)
    trend_reserve_usd: Mapped[float] = mapped_column(Float, default=0.0)
    updated_by: Mapped[str] = mapped_column(String(80), default="system")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=_now)


class BudgetReservation(Base):
    __tablename__ = "budget_reservations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), default=None, index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), default=None, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), default=None, index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(12), default="RESERVED")  # RESERVED|SETTLED|RELEASED
    actual_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AffiliateProgram(Base):
    __tablename__ = "affiliate_programs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    network: Mapped[str] = mapped_column(String(80), default="")
    tracking_template: Mapped[str] = mapped_column(Text, default="")
    default_disclosure: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AffiliateLink(Base):
    __tablename__ = "affiliate_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    program_id: Mapped[str] = mapped_column(ForeignKey("affiliate_programs.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), default=None)
    content_id: Mapped[str | None] = mapped_column(String(36), default=None)
    destination: Mapped[str] = mapped_column(Text)
    tracking_code: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SponsorDeal(Base):
    __tablename__ = "sponsor_deals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    sponsor: Mapped[str] = mapped_column(String(200))
    campaign_name: Mapped[str] = mapped_column(String(200), default="")
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deliverables: Mapped[dict] = mapped_column(JSON, default=dict)
    platforms: Mapped[list] = mapped_column(JSON, default=list)
    required_mentions: Mapped[list] = mapped_column(JSON, default=list)
    forbidden_claims: Mapped[list] = mapped_column(JSON, default=list)
    approval_required: Mapped[bool] = mapped_column(default=True)
    revenue_usd: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(12), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Offer(Base):
    __tablename__ = "offers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(24), default="PRODUCT")
    destination: Mapped[str] = mapped_column(Text, default="")
    cta: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentRoutingDecision(Base):
    __tablename__ = "content_routing_decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    topic: Mapped[str] = mapped_column(Text)
    candidate_id: Mapped[str | None] = mapped_column(String(36), default=None)
    routed_channel_id: Mapped[str | None] = mapped_column(String(36), default=None, index=True)
    routed_brand_id: Mapped[str | None] = mapped_column(String(36), default=None)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    cannibalization: Mapped[str] = mapped_column(String(24), default="SAFE")
    decision: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssetUsageHistory(Base):
    __tablename__ = "asset_usage_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), default=None)
    channel_id: Mapped[str | None] = mapped_column(String(36), default=None)
    campaign_id: Mapped[str | None] = mapped_column(String(36), default=None)
    scope: Mapped[str] = mapped_column(String(20), default="workspace")
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChannelReport(Base):
    __tablename__ = "channel_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    channel_id: Mapped[str] = mapped_column(String(36), index=True)
    period: Mapped[str] = mapped_column(String(12), default="weekly")
    period_start: Mapped[str] = mapped_column(String(10), default="")
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioReport(Base):
    __tablename__ = "portfolio_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    period: Mapped[str] = mapped_column(String(12), default="monthly")
    period_start: Mapped[str] = mapped_column(String(10), default="")
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


MB_TABLES = [
    "users", "workspaces", "workspace_members", "brands", "channels",
    "content_pillars", "channel_health_snapshots", "channel_operating_plans",
    "portfolio_snapshots", "portfolio_decisions", "budget_allocations",
    "budget_reservations", "affiliate_programs", "affiliate_links",
    "sponsor_deals", "offers", "content_routing_decisions", "asset_usage_history",
    "channel_reports", "portfolio_reports",
]

# NULLABLE tenant-scope columns added to pre-existing tables (0007 _ALTERS)
MB_ALTERS = [
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(36)",
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS brand_id VARCHAR(36)",
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS channel_id VARCHAR(36)",
    "ALTER TABLE platform_accounts ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(36)",
    "ALTER TABLE platform_accounts ADD COLUMN IF NOT EXISTS brand_id VARCHAR(36)",
    "ALTER TABLE cost_logs ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(36)",
    "ALTER TABLE cost_logs ADD COLUMN IF NOT EXISTS brand_id VARCHAR(36)",
    "ALTER TABLE cost_logs ADD COLUMN IF NOT EXISTS channel_id VARCHAR(36)",
    "ALTER TABLE revenue_entries ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(36)",
    "ALTER TABLE revenue_entries ADD COLUMN IF NOT EXISTS brand_id VARCHAR(36)",
    "ALTER TABLE revenue_entries ADD COLUMN IF NOT EXISTS channel_id VARCHAR(36)",
    "CREATE INDEX IF NOT EXISTS ix_campaigns_channel ON campaigns (channel_id)",
    "CREATE INDEX IF NOT EXISTS ix_cost_logs_channel ON cost_logs (channel_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_revenue_channel ON revenue_entries (channel_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS ix_budget_res_day ON budget_reservations (workspace_id, day, status)",
]
