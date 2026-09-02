# DISASTER RECOVERY

Phase 5. Companion to `RUNBOOK.md` (procedures) and `PRODUCTION_READINESS.md`
(gaps). Code is the source of truth: `backend/app/ops/backup.py`,
`backend/app/ops/storage_integrity.py`.

## Scope
What we protect, in priority order (from the Phase 5 mandate):
1. **Data loss** — Postgres (campaigns, publications, analytics, memory, audit) + `CRITICAL` assets.
2. **Duplicate posts** — idempotency keys, job leases, webhook-replay guard (survive restore).
3. **Secrets** — `ACF_MASTER_KEY` / `SECRET_KEY` are *not* in any backup; they must be recoverable from the secret store, independently.

## Recovery objectives (design targets)

| Metric | Target | Basis | Status |
|---|---|---|---|
| **RPO** (max data loss) | ≤ 24 h | Daily automated `pg_dump` (`ops-daily-backup` beat, 86400 s). | Met by design with local backups. **NEEDS_PRODUCTION_ENVIRONMENT** for the ≤ 5 min stretch goal — requires WAL archiving on a real PG host. |
| **RPO (assets)** | ≤ 24 h for `CRITICAL`; `REGENERATABLE` = 0 (rebuildable) | Daily storage tar; renders/thumbnails re-derived from campaign rows. | Met for `CRITICAL`; `REGENERATABLE` recovered by pipeline re-run. |
| **RTO** (time to restore service) | ≤ 60 min | Restore-into-separate-DB + rename swap, rehearsed in tests. | Met in local staging; a real cutover adds DNS/TLS/secret-store time not measured here. |
| **Backup verification lag** | every backup, automatically | `verify_backup()` runs in the daily task. | Met. |
| **Restore drill cadence** | monthly | `restore_to('acf_restore_test')`; `restore_tested_at` on the manifest. | Automated in `tests/ops/test_backup_restore.py`; schedule a monthly prod drill. |

## What is backed up

| Data | Method | Where | Frequency | Retention |
|---|---|---|---|---|
| Postgres (all tables incl. `audit_log`, `alembic_version`) | `pg_dump -Fc --no-owner --no-privileges` + sha256 + `BackupManifest` | `BACKUP_DIR` (mount durable storage; S3 slot exists, unconfigured) | daily + on-demand | `BACKUP_RETENTION_DAYS` (7) |
| Storage assets: `CRITICAL` (source uploads, masters), `REGENERATABLE` (renders, thumbnails) | `tar.gz`, classified by `storage_integrity.classify()` | same | daily | 7 |
| `CACHE` / `TEMP` assets | **not** backed up | — | — | — |
| Secrets (`ACF_MASTER_KEY`, `SECRET_KEY`, DB/Redis pw, OAuth client secrets) | **not** in backups — held in the secret store / `deploy/prod.env` | operator vault | on change | operator policy |
| Redis queue | not backed up; AOF (`appendonly yes`) for local durability | redis volume | continuous AOF | — |

Redis is deliberately not a DR target: publish jobs are idempotent and the Phase 2
crash-reconciler rebuilds queue state from Postgres.

## Failure scenarios & response

### S1 — Postgres data corruption / bad migration / accidental delete
RPO ≤ 24 h. Follow `RUNBOOK.md` → *DB restore*: restore latest `VERIFIED` backup
into `acf_restore_test`, let `restore_to()` re-check schema + counts, inspect,
rename-swap. Keep the broken DB 48 h.

### S2 — Full host loss
1. New host, install Docker, `git clone`.
2. Restore `deploy/prod.env` + Docker secrets from the vault (**not** from backups).
3. Copy the newest `*.dump` + `.sha256` from off-site storage into `backups/`.
4. `$COMPOSE up -d postgres redis` ; restore the dump into `acf` (fresh DB path in the runbook).
5. Restore the storage tar over `/app/storage`; `POST /api/ops/storage/integrity`.
6. `$COMPOSE up -d` ; `/health/ready` ; re-point DNS / re-issue TLS.
7. `POST /api/ops/workers/scan-stuck` ; verify a DRY_RUN preflight.
RTO dominated by off-site fetch + DNS/TLS.

### S3 — Storage volume loss, DB intact
Restore the storage tar. Regenerate `REGENERATABLE` assets by re-running the media
pipeline for campaigns whose `scan_assets()` reports `MISSING_ASSET`. No DB restore.

### S4 — `ACF_MASTER_KEY` lost
Stored OAuth tokens become undecryptable. DB/asset data is fine. Recovery =
rotate in a new key and force every platform account through OAuth reconnect
(`RUNBOOK.md` → *OAuth reconnect*). This is why the key must live in a vault with
its **own** backup, separate from the DB.

### S5 — Ransomware / malicious deletion of local backups
Mitigation: off-site/object-storage copy with versioning + object lock
(**NEEDS_PRODUCTION_ENVIRONMENT** — not configured here). Until then, local
backups share fate with the host; treat S2 as the recovery path from the last
off-host copy.

### S6 — Duplicate posts after a restore
Restoring an older DB can re-open jobs that already published. Guards that hold:
`publish_jobs.idempotency_key` unique index, `publications.publish_job_id` unique,
webhook-replay `WEBHOOK_<state>` event check, and remote verification (Phase 2)
before re-send. After any restore: run with `DRY_RUN=true` first, review
`/api/ops/status` + scheduled jobs, then re-enable live publishing.

## Restore drill (monthly, ~15 min)
1. `POST /api/ops/backups/run {"kind":"full"}` → note id.
2. `POST /api/ops/backups/<id>/verify` → expect `VERIFIED`.
3. `restore_to('<id>', 'acf_restore_test')` → expect `RESTORE_TESTED`,
   `migration_revision` `0006*`, table counts > 0, marker/spot-check row present.
4. Record the date in the run log; confirm `restore_tested_at` on the manifest.
5. Drop `acf_restore_test`.
`tests/ops/test_backup_restore.py` performs 1–3 on every CI run; the monthly item
is doing it against **production** data volume.

## Contacts / escalation
Operator-defined. Fill in before go-live: on-call, DB owner, platform-account
owner, secret-store custodian.
