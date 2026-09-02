"""Cross-Phase Intelligence Upgrade — URL learning / reference dataset / prompt
distillation / agent skill learning / platform selection (additive).

Revision ID: 0009_intelligence
Revises: 0008_governance
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models_learn import LEARN_ALTERS, LEARN_TABLES

revision: str = "0009_intelligence"
down_revision: str | None = "0008_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in LEARN_TABLES])
    for stmt in LEARN_ALTERS:
        op.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    for stmt in reversed(LEARN_ALTERS):
        if stmt.startswith("CREATE INDEX"):
            name = stmt.split("EXISTS ")[1].split(" ")[0]
            op.execute(f"DROP INDEX IF EXISTS {name}")
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[t] for t in reversed(LEARN_TABLES)])
