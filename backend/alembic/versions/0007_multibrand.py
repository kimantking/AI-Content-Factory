"""Phase 6 multi-brand / multi-channel / portfolio / monetization schema.

Additive only: 20 new tables + NULLABLE tenant-scope columns on
campaigns / platform_accounts / cost_logs / revenue_entries. No destructive DDL.

Revision ID: 0007_multibrand
Revises: 0006_production
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models_mb import MB_ALTERS, MB_TABLES

revision: str = "0007_multibrand"
down_revision: str | None = "0006_production"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in MB_TABLES])
    for stmt in MB_ALTERS:
        op.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    for stmt in reversed(MB_ALTERS):
        if stmt.startswith("CREATE INDEX"):
            name = stmt.split("EXISTS ")[1].split(" ")[0]
            op.execute(f"DROP INDEX IF EXISTS {name}")
        # ADD COLUMN IF NOT EXISTS are left in place (harmless, NULLABLE)
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[t] for t in reversed(MB_TABLES)])
