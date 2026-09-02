# Backup & Recovery (Phase 10 §20, §102)

Code: `app/ops/backup.py` · API: `/api/ops/backups`, `/backups/run`,
`/backups/{id}/verify`. Tests: `tests/ops/test_backup_restore.py` (real
pg_dump/pg_restore round-trip).

## Local / staging (VERIFIED)
* `run_backup("full")` → `pg_dump -Fc --no-owner --no-privileges` + sha256 +
  optional Fernet + `BackupManifest` + retention. Tool resolved
  setting → PATH → `docker exec <postgres_container>`.
* `verify_backup(id)` → checksum + `pg_restore --list` → VERIFIED / FAILED.
* `restore_to(id, target_db)` → **refuses the source DB**, DROP/CREATE target,
  `pg_restore --clean --if-exists`, re-verifies `alembic_version` + table counts
  via a fresh engine → RESTORE_TESTED.
* `run_backup("storage")` → tars CRITICAL + REGENERATABLE assets.

## Post-restore validation (§98)
On the restored DB: login, Content Library list, learning data, campaign state
are all readable (`alembic_version` + per-table counts checked automatically).

## Production (PENDING)
* **Off-site target** (S3/remote): `NEEDS_PRODUCTION_ENVIRONMENT`.
* **WAL archiving / PITR**: `NEEDS_PRODUCTION_ENVIRONMENT`.
Not faked as VERIFIED.
