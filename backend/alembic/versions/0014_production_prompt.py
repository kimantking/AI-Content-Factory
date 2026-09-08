"""Persist a creative brief independently of the research topic."""
import sqlalchemy as sa
from alembic import op

revision = "0014_production_prompt"
down_revision = "0013_scene_motion_text"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("campaigns", sa.Column("production_prompt", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("campaigns", "production_prompt")
