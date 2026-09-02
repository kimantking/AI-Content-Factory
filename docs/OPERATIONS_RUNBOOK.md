# Operations Runbook (Phase 9)

Failure-mode playbook, informed by the Phase 9 fault-injection results. Extends
`docs/RUNBOOK.md` (routine start/stop/deploy) — this file is the "something is
wrong" reference. Ops API base `/api/ops`; admin UI `/admin`.

Every failure below has been exercised (mock/controlled) — see
`docs/FAILURE_RECOVERY.md` / `docs/CHAOS_TESTING.md` for the test that proves the
recovery.

---

## Local stack (Windows dev)

- Start: `cd C:\AI-Content-Factory ; .\scripts\start-local.ps1` — verifies Docker Desktop
  and host Ollama (`http://localhost:11434` + `gemma3:4b`), runs `docker compose config -q`,
  builds **all** images (`backend` and `worker` are separate images — build with no service
  arg), `up -d`, waits for per-service health, prints a summary, opens `http://localhost:3000`.
- Stop: `.\scripts\stop-local.ps1` (`stop`) / `-Down` (`down`). **Never `-v`** — `pgdata` is kept.
- Status: `.\scripts\status-local.ps1` — read-only; container health, `/health/ready`,
  dashboard HTTP, host Ollama + `gemma3:4b`, `/api/providers` (status only, never a key).
- `.env` is the source of truth. `docker-compose.yml` (git-untracked) uses `env_file: .env`
  plus `${VAR:-default}` in `environment:`; it pins only service-name DB/Redis URLs and
  `OLLAMA_BASE_URL=http://host.docker.internal:11434` + `extra_hosts: host-gateway`.
- Known-good fixes baked in: worker healthcheck is `celery inspect ping` (the image's
  inherited HTTP `/health/live` check is backend-only); worker id is the stable
  `ACF_WORKER_ID`/hostname (prefork children no longer register duplicates → snapshot
  Workers/Scheduler stays OK); frontend sets `HOSTNAME=0.0.0.0` so the in-container
  healthcheck reaches the Next standalone server; the frontend has **no `command:`
  override** — it must keep `node server.js` (`npm run start` → `sh: next: not found`).

### Running the backend test suite (do NOT run it against a live stack)

`backend/tests/conftest.py::_clean_db` is autouse and runs
`TRUNCATE <~90 domain tables> RESTART IDENTITY CASCADE` **before every test**,
taking `ACCESS EXCLUSIVE` on all of them. It uses the app's own engine, i.e. the
same `acf` database the running `backend` + `worker` (embedded beat) use. If the
live services are up during a test run, a beat heartbeat / publish tick / support
-snapshot read will overlap a test's wide transaction and the two deadlock —
Postgres kills one with `DeadlockDetected` or an idle-in-transaction termination.
This is a **test-harness** collision, not a production bug (production issues no
`TRUNCATE` and runs no second client). See
`backend/tests/test_conftest_baseline.py` for the full root-cause note.

Correct way to run the suite locally (keeps `pgdata` / Redis — no volume loss):

```
docker compose stop backend worker          # postgres + redis stay up
docker compose run --rm --no-deps backend sh -c "cd /app && python -m pytest -q tests/"
docker compose up -d backend worker
```

`_base_settings` also forces `ollama_enabled = False` for the whole suite so the
router never dispatches to the real local model (slow, non-deterministic, widens
the transaction window). Real-Ollama checks live in `tests/ai_router/test_ollama.py`
behind an `@ollama_available` sk-if and construct `OllamaLLMProvider` directly.

## Backend restart
- `$COMPOSE restart backend` (or `up -d`). `alembic upgrade head` runs on boot.
- In-flight LangGraph campaigns resume from their last checkpoint on the next
  `run_campaign_task` / manual `POST /api/campaigns/{id}/resume` — **no duplicate
  provider calls** (thread_id = campaign_id).
- Verify: `curl -fsS localhost:8000/health/ready`.

## Worker restart / crash
- `$COMPOSE restart worker`. A killed worker's job returns to the queue
  (at-least-once). Idempotency: `PublishJob.idempotency_key` + `remote_post_id`
  and the media node's `_existing_scene_asset` reuse mean a re-run produces **no
  duplicate remote posts or paid regenerations**.
- Stuck jobs: `POST /api/ops/workers/scan-stuck` re-queues jobs whose lease
  expired; `GET /api/ops/dlq` lists dead-lettered jobs (`/{id}/retry`).

## Redis issue
- `readiness()` shows `checks.redis.status = DOWN`; the API and inline campaign
  execution keep working. Celery-dispatched work pauses until Redis returns.
- `$COMPOSE restart redis`; workers reconnect automatically. Queued jobs are
  Redis-persisted (AOF in the prod overlay).

## DB issue
- `pool_pre_ping=True` transparently reconnects after a blip / restart. A
  `statement_timeout` (prod overlay) prevents a runaway query pinning a
  connection.
- After a restart: `curl /health/ready` → confirm `database.status = OK`;
  `alembic current` should be `0011_medium_repair`.
- Long "idle in transaction": `SELECT pg_terminate_backend(pid) …` (see RUNBOOK).

## Ollama issue
- `GET /api/local-ai/status` → `NOT_RUNNING` / model missing. App never crashes.
- With `ALLOW_CLOUD_FALLBACK=true`: allowed tasks fall back to a cloud model.
- With `LOCAL_ONLY` (`ALLOW_CLOUD_FALLBACK=false`): local-tier tasks fail cleanly
  (no silent cloud spend). Restart Ollama, then `GET /api/models?refresh=true` to
  re-enable local routing.

## Provider outage (LLM / search / media)
- Retryable (`TIMEOUT`, `RATE_LIMIT`) → automatic backoff (3 attempts).
- `AUTH_ERROR` / `BUDGET_EXCEEDED` → not retried; job → FAILED with an
  actionable `error_type`; **never a fake success**.
- Search unavailable → `INSUFFICIENT_RESEARCH`; the campaign stops before writing
  a script.

## Render failure (FFmpeg)
- Bad input / timeout / non-zero exit → the scene is marked failed;
  `run_media_pipeline(resume=True)` rebuilds only the failed scene + composition
  (Smart-Rerender). Completed scene assets are retained.
- Check `GET /api/library/{id}/media/video` and the campaign's `MediaTask` rows.

## Storage issue
- Post-render write failure → the asset is **not** marked AVAILABLE; the library
  card shows `has_video=false` / `MISSING_ASSET`. Re-run the render.
- Partial file → Technical QA flags it; disk-low → guard blocks new renders.
- `GET /api/ops/storage/integrity` sweeps for DB rows with a missing file.

## Publish failure
- Timeout after the remote accepted → crash-reconcile adopts the existing post
  on the next run (`reconcile_job`); no double post.
- Repeated failure → dead-letter after `publish_max_attempts`; `GET /api/ops/dlq`.
- Platform turned off after queue → job → `BLOCKED` (`PLATFORM_DESELECTED`), 0
  remote.

## Token expiration
- `ensure_valid` refreshes once; if refresh fails the account →
  `NEEDS_REAUTH` and jobs stop (no fake SUCCESS). Operator re-connects via the
  OAuth flow in `/admin`.

## Stuck campaign
- `GET /api/campaigns/{id}` shows `current_step`; if unchanged for long,
  `POST /api/campaigns/{id}/resume` (idempotent). Persistent → check
  `AgentRun` / `ErrorLog` for the failing node.

## Budget block
- Campaign hits `campaign_budget_usd` / brand / workspace hard limit → new paid
  calls blocked, completed assets kept. Raise the limit (config or
  `POST /api/portfolio/budget`) then resume. Concurrent campaigns share the limit
  transactionally.

## Governance block
- `decision = BLOCK / FIX_REQUIRED / HUMAN_REVIEW` → never PUBLISHED. Use
  `/api/governance/cases` + `/api/governance/cases/{id}/review` (approve/repair).
  `POST /api/governance/repair` runs the deterministic repair (asset replace /
  disclosure add).
- Stale platform policy → `GET /api/policy/verification` shows the review queue;
  a named reviewer attests via `POST /api/policy/verify` (AUDIT-P7-001).

## Backup / restore
- `POST /api/ops/backups/run` (`full` | `storage`); `GET /api/ops/backups` +
  `/{id}/verify` (checksum + `pg_restore --list`).
- Restore into a **separate** DB: `restore_to(backup_id, target_db)` refuses the
  source DB, DROP/CREATE target, `pg_restore --clean --if-exists`, re-verifies
  `alembic_version` + table counts.
- Off-site / WAL / PITR: **NEEDS_PRODUCTION_ENVIRONMENT** — not configured here.

---

## Production kill switches (Phase 10)

DB-backed (`app/ops/runtime_flags.py`), survive a restart, wired to real gates.
Toggle: `POST /api/ops/flags/<FLAG> {"enabled": true|false, "confirm": true}`
(enabling requires `confirm`). All reachable from mobile via `/support` / `/admin`.

| Flag | Effect | Verify |
|---|---|---|
| `GLOBAL_PUBLISH_PAUSE` | `run_publish_job` short-circuits before any remote work; job stays `READY` (not failed) | `tests/phase10/test_kill_switches.py` |
| `GLOBAL_PAID_PROVIDER_PAUSE` | `ai_router.execute._provider_for("…","anthropic")` raises; local Ollama + mock still returned | same |
| `EMERGENCY_STOP` | autopilot halt + publish pause | Phase 4 |
| `SAFE_MODE` | no new autopilot production | Phase 5 |
| `MAINTENANCE_MODE` | `/health/ready` → not ready | Phase 5 |

## User support procedure (§102)

1. User opens the dashboard → **AI 지원 스냅샷** (`/support`).
2. **[캡처 모드]** → screenshot; or **[지원 정보 복사]** → paste into ChatGPT / send to admin.
3. The snapshot carries: overall health, current job + pipeline, model routing,
   Ollama, workers/queues, **last error with a normalised code + a one-line
   suggested action**, governance/SNS/cost, trace id. No secrets, own workspace only.
4. If the suggested action doesn't resolve it, escalate with the screenshot +
   copied text + `trace_id`.
