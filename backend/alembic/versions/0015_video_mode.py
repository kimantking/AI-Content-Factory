"""Persist explicit video generation choice; legacy campaigns retain old settings."""
import sqlalchemy as sa
from alembic import op

revision = "0015_video_mode"
down_revision = "0014_production_prompt"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("campaigns")}
    if "video_mode" not in columns:
        op.add_column("campaigns", sa.Column("video_mode", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("campaigns", "video_mode")
