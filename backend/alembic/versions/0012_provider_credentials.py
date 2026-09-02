"""Phase 11 — provider credential vault (additive).

Revision ID: 0012_provider_credentials
Revises: 0011_medium_repair
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db import models  # noqa: F401  — registers every model on Base
from app.db.base import Base
from app.db.models_p11 import P11_TABLES

revision: str = "0012_provider_credentials"
down_revision: str | None = "0011_medium_repair"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in P11_TABLES])


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[t] for t in reversed(P11_TABLES)])
