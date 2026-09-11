"""Persist the explicitly selected Veo generation allowance."""
import sqlalchemy as sa
from alembic import op

revision = "0016_video_plan"
down_revision = "0015_video_mode"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("campaigns", sa.Column("video_plan", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("campaigns", "video_plan")
