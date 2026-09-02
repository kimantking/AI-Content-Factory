"""initial Phase 1-A schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-31
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db.base import Base
from app.db import models  # noqa: F401

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables owned by this migration (LangGraph checkpoint tables are created by the
# PostgresSaver.setup() call at runtime and are intentionally not managed here).
_TABLES = [
    "campaigns", "research_sources", "verified_facts", "strategies", "hooks",
    "scripts", "agent_runs", "prompt_versions", "cost_logs", "errors",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in _TABLES])


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[t] for t in _TABLES])
