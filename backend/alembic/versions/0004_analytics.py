"""Phase 3 analytics / learning / memory / revenue schema

Revision ID: 0004_analytics
Revises: 0003_publishing
Create Date: 2026-08-31
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db import models  # noqa: F401
from app.db.base import Base

revision: str = "0004_analytics"
down_revision: str | None = "0003_publishing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "metric_catalog", "analytics_snapshots", "analytics_jobs", "content_features",
    "performance_scores", "revenue_entries", "cost_allocations", "learning_memories",
    "content_recipes", "experiments", "experiment_results", "daily_learning_runs",
    "period_reports",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in _TABLES])


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[t] for t in _TABLES])
