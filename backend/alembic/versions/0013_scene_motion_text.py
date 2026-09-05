"""Widen scene motion fields used by the visual director.

Revision ID: 0013_scene_motion_text
Revises: 0012_provider_credentials
Create Date: 2026-09-05
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_scene_motion_text"
down_revision: str | None = "0012_provider_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "scenes", "camera_motion",
        existing_type=sa.String(length=24), type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.alter_column(
        "scenes", "motion_effect",
        existing_type=sa.String(length=24), type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "scenes", "motion_effect",
        existing_type=sa.Text(), type_=sa.String(length=24),
        existing_nullable=False,
    )
    op.alter_column(
        "scenes", "camera_motion",
        existing_type=sa.String(length=64), type_=sa.String(length=24),
        existing_nullable=False,
    )
