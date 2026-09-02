"""Phase 8 — Model Router telemetry + performance memory (additive).

Registered on the shared Base via app.db.models.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models import _now, _uuid


class ModelRoutingEvent(Base):
    __tablename__ = "model_routing_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), index=True)
    agent_type: Mapped[str] = mapped_column(String(48), index=True)
    task_type: Mapped[str] = mapped_column(String(48), index=True)
    tier: Mapped[str] = mapped_column(String(20), default="")
    model_id: Mapped[str] = mapped_column(String(80), index=True)
    provider: Mapped[str] = mapped_column(String(24), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_state: Mapped[str] = mapped_column(String(12), default="UNKNOWN")
    schema_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    quality_signal: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1 if known
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    error_type: Mapped[str] = mapped_column(String(32), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    # AUDIT-P8-006 — which PromptComposer output shaped this call's system prompt
    # {prompt_composer_used, skill_ids, blueprint_ids, memory_ids, prompt_version,
    #  context_tokens, truncated}
    prompt_lineage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelPerformance(Base):
    __tablename__ = "model_performance"
    __table_args__ = (UniqueConstraint("model_id", "task_type", name="uq_model_task_perf"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    model_id: Mapped[str] = mapped_column(String(80), index=True)
    task_type: Mapped[str] = mapped_column(String(48), index=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    schema_valid_rate: Mapped[float] = mapped_column(Float, default=0.0)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    avg_quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    strength: Mapped[str] = mapped_column(String(16), default="UNKNOWN")  # STRONG|OK|WEAK|UNKNOWN
    benchmark_state: Mapped[str] = mapped_column(String(16), default="NONE")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now)


P8_TABLES = ["model_routing_events", "model_performance"]
P8_ALTERS = [
    "CREATE INDEX IF NOT EXISTS ix_routing_model_task ON model_routing_events (model_id, task_type)",
]

# AUDIT-P8-006 baseline-hardening — additive only, applied by migration 0011.
P8B_ALTERS = [
    "ALTER TABLE model_routing_events ADD COLUMN IF NOT EXISTS prompt_lineage JSON",
]
