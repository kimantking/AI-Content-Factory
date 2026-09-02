"""Phase 2 publishing schema

Revision ID: 0003_publishing
Revises: 0002_media
Create Date: 2026-08-31
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db import models  # noqa: F401
from app.db.base import Base

revision: str = "0003_publishing"
down_revision: str | None = "0002_media"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "platform_accounts", "oauth_states", "publish_jobs",
    "publications", "publication_events", "publish_audits",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in _TABLES])


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[t] for t in _TABLES])
