"""Phase 4 trend intelligence / autopilot schema

Revision ID: 0005_autopilot
Revises: 0004_analytics
Create Date: 2026-08-31
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db import models  # noqa: F401
from app.db.base import Base

revision: str = "0005_autopilot"
down_revision: str | None = "0004_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "trend_sources", "raw_trend_events", "topic_candidates", "autopilot_runs",
    "autopilot_decisions", "autopilot_config_versions", "topic_rejections",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in _TABLES])


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[t] for t in _TABLES])
