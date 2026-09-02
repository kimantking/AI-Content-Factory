"""Phase 8 — model router telemetry + performance memory (additive).

Revision ID: 0010_phase8
Revises: 0009_intelligence
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models_p8 import P8_ALTERS, P8_TABLES

revision: str = "0010_phase8"
down_revision: str | None = "0009_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in P8_TABLES])
    for stmt in P8_ALTERS:
        op.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    for stmt in reversed(P8_ALTERS):
        if stmt.startswith("CREATE INDEX"):
            name = stmt.split("EXISTS ")[1].split(" ")[0]
            op.execute(f"DROP INDEX IF EXISTS {name}")
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[t] for t in reversed(P8_TABLES)])
