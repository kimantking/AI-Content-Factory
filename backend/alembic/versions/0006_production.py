"""Phase 5 production / ops schema + integrity constraints

Revision ID: 0006_production
Revises: 0005_autopilot
Create Date: 2026-08-31
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db import models  # noqa: F401
from app.db.base import Base

revision: str = "0006_production"
down_revision: str | None = "0005_autopilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "runtime_settings", "config_change_log", "workers", "job_leases",
    "backup_manifests", "ops_alerts", "audit_log", "dead_letters",
]

# integrity constraints on pre-existing tables (idempotency / no-duplicate)
_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_publish_jobs_idem "
    "ON publish_jobs (idempotency_key) WHERE idempotency_key <> ''",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshot_window "
    "ON analytics_snapshots (publication_id, window_label) WHERE window_label <> ''",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_publication_job "
    "ON publications (publish_job_id)",
    "CREATE INDEX IF NOT EXISTS ix_publish_jobs_status_sched "
    "ON publish_jobs (status, scheduled_at)",
    "CREATE INDEX IF NOT EXISTS ix_analytics_jobs_due "
    "ON analytics_jobs (status, scheduled_at)",
    "CREATE INDEX IF NOT EXISTS ix_topic_candidates_run_status "
    "ON topic_candidates (run_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_cost_logs_campaign_created "
    "ON cost_logs (campaign_id, created_at)",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in _TABLES])
    for stmt in _INDEXES:
        op.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    for stmt in _INDEXES:
        name = stmt.split("EXISTS ")[1].split(" ")[0]
        op.execute(f"DROP INDEX IF EXISTS {name}")
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[t] for t in _TABLES])
