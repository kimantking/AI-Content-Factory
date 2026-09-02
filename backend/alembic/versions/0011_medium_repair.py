"""MEDIUM gap repair — Phase 1-8 baseline hardening (additive).

AUDIT-P8-006: prompt_lineage on model_routing_events so a routed agent call can
record which PromptComposer output (skills / blueprints / memory / version /
token budget) shaped its system prompt.

Revision ID: 0011_medium_repair
Revises: 0010_phase8
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db import models  # noqa: F401
from app.db.models_p8 import P8B_ALTERS

revision: str = "0011_medium_repair"
down_revision: str | None = "0010_phase8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for stmt in P8B_ALTERS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("ALTER TABLE model_routing_events DROP COLUMN IF EXISTS prompt_lineage")
