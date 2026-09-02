"""Phase 7 — content governance / rights / policy / originality schema (additive).

Revision ID: 0008_governance
Revises: 0007_multibrand
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models_gov import GOV_ALTERS, GOV_TABLES

revision: str = "0008_governance"
down_revision: str | None = "0007_multibrand"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in GOV_TABLES])
    for stmt in GOV_ALTERS:
        op.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    for stmt in reversed(GOV_ALTERS):
        if stmt.startswith("CREATE INDEX"):
            name = stmt.split("EXISTS ")[1].split(" ")[0]
            op.execute(f"DROP INDEX IF EXISTS {name}")
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[t] for t in reversed(GOV_TABLES)])
