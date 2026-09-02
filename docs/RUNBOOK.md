# RUNBOOK

Operational procedures for AI Content Factory (Phase 5).
All commands assume the repo root and the production overlay:

```
export COMPOSE="docker compose --env-file deploy/prod.env -f docker-compose.yml -f docker-compose.prod.yml"
```

`deploy/prod.env` is operator-supplied (see `.env.example` for the names) and is
git-ignored. Local/dev = drop `--env-file` and the prod file.

Ops API base: `/api/ops` (put an auth boundary in front of it — see
`DEPLOYMENT_CHECKLIST.md`). Frontend: `/admin`.

---

## Routine operations

### Start
```
$COMPOSE up -d
$COMPOSE ps
curl -fsS localhost:8000/health/ready | jq
```
`backend` runs `alembic upgrade head` on boot. Wait for `/health/ready` → `{"ready": true}`.

### Stop (graceful)
```
$COMPOSE stop            # SIGTERM; Celery finishes in-flight tasks, releases leases
```
Full teardown (keeps volumes): `$COMPOSE down`. **Never** `down -v` in prod — that deletes `pgdata`.

### Restart one service
```
$COMPOSE restart backend
$COMPOSE restart worker worker-media worker-analytics worker-autopilot
```

### Deploy a new version
1. `git pull` on the host.
2. Snapshot first: `curl -XPOST localhost:8000/api/ops/backups/run -d '{"kind":"full"}' -H 'content-type: application/json'`
3. Enable maintenance mode (below).
4. `$COMPOSE build backend worker` (workers share the backend image).
5. `$COMPOSE up -d` — migrations run automatically.
6. `curl -fsS localhost:8000/health/ready` and check `/api/ops/status`.
7. Disable maintenance mode. Watch `/metrics` `acf_http_5xx_total` for 10 min.

### Rollback
1. Maintenance mode ON.
2. `git checkout <previous-tag>` ; `$COMPOSE build backend worker`.
3. **If the new version added a migration**, restore the pre-deploy backup
   (see *DB restore*) — do not run `alembic downgrade` blind on a schema that
   already took writes. If no migration ran, just `up -d` the old image.
4. `up -d`, verify health, maintenance mode OFF.

---

## Maintenance mode
Returns 503 for app routes; `/health/*`, `/metrics`, `/api/ops/*` stay up. Survives restart.
```
curl -XPOST localhost:8000/api/ops/flags/MAINTENANCE_MODE -H 'content-type: application/json' -d '{"enabled":true,"confirm":true}'
# ... work ...
curl -XPOST localhost:8000/api/ops/flags/MAINTENANCE_MODE -H 'content-type: application/json' -d '{"enabled":false}'
```
Or the `/admin` page → Runtime Flags.

## Safe mode
Autopilot production **HOLD**s (no new campaigns/posts); everything else runs. Survives restart.
```
curl -XPOST localhost:8000/api/ops/flags/SAFE_MODE -H 'content-type: application/json' -d '{"enabled":true,"confirm":true}'
```
Use when a provider is flaky or spend looks wrong but you don't want a full stop.

## Emergency stop (autopilot)
Hard stop: refuses new autopilot runs, cancels SELECTED candidates, holds
READY/SCHEDULED/QUEUED publish jobs. **Never** touches a job already
UPLOADING/PROCESSING on a platform. Survives restart (persisted flag).
```
curl -XPOST localhost:8000/api/autopilot/emergency-stop
# resume when safe:
curl -XPOST localhost:8000/api/autopilot/resume-stop
```
`/autopilot` page → **AUTOPILOT 긴급 중지**.

---

## DB backup (manual)
```
curl -XPOST localhost:8000/api/ops/backups/run -H 'content-type: application/json' -d '{"kind":"full"}'
curl localhost:8000/api/ops/backups | jq '.recent[0]'      # note the id
curl -XPOST localhost:8000/api/ops/backups/<id>/verify | jq # expect status VERIFIED
```
Files: `backend/backups/` (mount durable storage here in prod). Each has a
`.dump` (`pg_dump -Fc`), a sha256, and a `BackupManifest` row.
Daily automatic backup: Celery beat `ops-daily-backup` → full + verify + storage.
Retention: `BACKUP_RETENTION_DAYS` (default 7); `_apply_retention()` prunes files + manifests.

CLI fallback if the API is down:
```
$COMPOSE exec postgres pg_dump -U acf -Fc --no-owner --no-privileges acf > backups/manual_$(date +%F).dump
sha256sum backups/manual_*.dump > backups/manual_$(date +%F).dump.sha256
```

## DB restore  (destructive — read all steps first)
`restore_to()` refuses to touch the live DB; it always restores into a **separate**
database so you can inspect before cutover.

1. Maintenance mode ON; `$COMPOSE stop worker worker-media worker-analytics worker-autopilot`.
2. Restore into the test DB and let the code re-verify schema + row counts:
   ```
   $COMPOSE exec backend python -c "from app.ops.backup import restore_to; import json; print(json.dumps(restore_to('<backup_id>', 'acf_restore_test'), default=str))"
   ```
   Expect `status: RESTORE_TESTED`, `migration_revision` starting `0006`, table counts non-zero.
3. Inspect `acf_restore_test` manually if you need to (`$COMPOSE exec postgres psql -U acf acf_restore_test`).
4. Cut over — pick one:
   - **Rename swap** (fastest): stop `backend`; in `psql`:
     `ALTER DATABASE acf RENAME TO acf_broken_<date>; ALTER DATABASE acf_restore_test RENAME TO acf;`
   - **Fresh restore into acf**: drop/recreate `acf`, then
     `$COMPOSE exec postgres pg_restore -U acf -d acf --clean --if-exists /path/to.dump`
     (copy the dump into the container first, or restore from the host client).
5. `$COMPOSE up -d`; `/health/ready`; start workers; maintenance mode OFF.
6. Keep `acf_broken_<date>` for 48 h, then drop.

RPO/RTO targets and the full drill: `DISASTER_RECOVERY.md`.

## Storage / asset restore
```
$COMPOSE exec backend python -c "from app.ops.backup import run_backup; print(run_backup('storage'))"   # to make one
# to restore: extract the tar.gz over /app/storage, then:
curl -XPOST localhost:8000/api/ops/storage/integrity | jq
```
`scan_assets()` reports `MISSING_ASSET` / `CORRUPTED`. `REGENERATABLE` assets
(renders, thumbnails) can be rebuilt by re-running the media pipeline for the
affected campaign instead of restoring.

---

## Incident procedures

### Redis is down
- Symptom: `/health/ready` → 503, `dependencies.redis.status = ERROR`; Celery not consuming.
- Web API keeps serving reads that don't need the queue.
- Fix: `$COMPOSE restart redis`. AOF (`appendonly yes`) replays enqueued jobs.
- If the AOF is corrupt: `redis-check-aof --fix`, or accept queue loss — publish
  jobs are idempotent and the crash-reconciler re-derives state from Postgres.
- After recovery: `curl -XPOST localhost:8000/api/ops/workers/scan-stuck`.

### A worker is stuck / dead
- `/api/ops/workers` shows `STALE` (heartbeat > `WORKER_HEARTBEAT_STALE_S`) or `DEAD`.
- `curl -XPOST localhost:8000/api/ops/workers/scan-stuck` — releases expired
  `job_leases` (only expired ones), raises a HIGH alert with what was recovered.
- `$COMPOSE restart <worker-service>`. On shutdown it releases its own leases as `RECOVERED`.
- Duplicate execution is prevented by the lease unique constraint regardless.

### Queue backlog
- `/api/ops/queues` → `HOLD` means depth ≥ `QUEUE_BACKPRESSURE_HOLD`; autopilot
  production is already auto-paused (`stage="backpressure"`).
- Scale the hot queue: `$COMPOSE up -d --scale worker-media=3`.
- Check for a poison message: `/api/ops/dlq` — retry the retryable, resolve the rest.
- If spend is the concern, add SAFE_MODE while you drain.

### Publisher / platform failure
- Phase 2 retry + DLQ handle transient errors. `AUTH_REVOKED` / `POLICY_REJECTION`
  → non-retryable, lands in DLQ, WARNING alert.
- Reconnect OAuth: `/publishing` page → the account → reconnect (or
  `POST /api/publishing/accounts/<platform>/connect`). Then `POST /api/ops/dlq/<id>/retry`.
- Platform-wide outage: SAFE_MODE, let scheduled jobs wait; they are not lost.

### Provider (LLM / search / media) failure
- Circuit breaker opens after `PROVIDER_BREAKER_THRESHOLD` failures →
  `CircuitOpen` fast-fail for `PROVIDER_BREAKER_COOLDOWN_S`.
- `/api/ops/deep-health?force=true` to see live provider state.
- If it's cost, not errors: `/api/ops/cost-anomaly/check`.
- Prolonged outage: SAFE_MODE (autopilot holds); manual campaigns still allowed.

### Disk full
- `dependencies.storage` → `WARNING` at `DISK_WARN_PCT` (85%), `CRITICAL` at 95%; alert fired.
- Prune old backups (retention should, but): delete `backups/*.dump` older than policy + their manifests.
- Clear `TEMP` / `CACHE` assets: `scan_assets()` classifies them; safe to delete.
- Rotate logs (`*.log`), `docker system prune -f` on the host.

### Cost anomaly alert
- `/api/ops/alerts` shows the fingerprint (campaign / provider / llm-token-surge).
- Confirm with `/api/ops/cost-anomaly/check`.
- Immediate brake: `/api/autopilot/emergency-stop` (stops new spend) or SAFE_MODE.
- HARD budgets are AI-immutable; only `actor="user"` can raise them (`/api/autopilot/config`).

### Secret rotation
1. Generate the new value. For `ACF_MASTER_KEY`, keep the **old** key available as
   the previous key id — `TokenManager` decrypts old, encrypts new.
2. Update the Docker secret / `deploy/prod.env`.
3. Rolling restart: `$COMPOSE up -d backend worker ...`.
4. Re-encrypt stored OAuth tokens:
   `$COMPOSE exec backend python -m app.publishing.reencrypt_tokens` (Phase 2 helper)
   — or force each account through reconnect.
5. Verify: `/api/ops/status` clean, a DRY_RUN publish preflight passes.
6. The rotation is recorded in `audit_log`. Retire the old key after all tokens are re-encrypted.

`SECRET_KEY` rotation invalidates existing sessions/CSRF tokens — expect re-login.

### OAuth reconnect (token expired / revoked)
- `/publishing` page flags the account; `PublicationEvent` / DLQ shows `AUTH_REVOKED`.
- Operator completes the OAuth flow (real credentials required — otherwise MOCK).
- `POST /api/ops/dlq/<id>/retry` for jobs that failed on it.

### Autopilot recovery (after a pause)
- `/autopilot` shows `PAUSED` + the watchdog trigger (runaway cost / post limit /
  duplicates / QA-failure rate / repeated auth failure).
- Address the trigger (top up budget via config as `user`, fix auth, etc.).
- Resume: `POST /api/autopilot/resume-stop` (if it was an emergency stop) or set
  the mode again. Runs are resumable by `resume_run_id` — no duplicate campaigns
  (bridge is idempotent by `candidate_id`).

---

## Quick reference
| Need | Command |
|---|---|
| Is it up? | `curl -fsS localhost:8000/health/ready` |
| Full status | `curl localhost:8000/api/ops/status \| jq` |
| Metrics | `curl localhost:8000/metrics` |
| Make a backup | `curl -XPOST .../api/ops/backups/run -d '{"kind":"full"}' -H 'content-type: application/json'` |
| Stop the world (autopilot) | `curl -XPOST .../api/autopilot/emergency-stop` |
| Maintenance ON | `curl -XPOST .../api/ops/flags/MAINTENANCE_MODE -d '{"enabled":true,"confirm":true}' -H 'content-type: application/json'` |
| Recover stuck jobs | `curl -XPOST .../api/ops/workers/scan-stuck` |
| Logs (one service) | `$COMPOSE logs -f --tail=200 backend` |
