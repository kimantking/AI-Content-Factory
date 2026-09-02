# PRODUCTION READINESS

Phase 5. Status vocabulary: **READY** (works in prod today) ·
**PARTIAL** (works, but a gap remains) · **NOT_READY** (blocks go-live) ·
**NEEDS_PRODUCTION_ENVIRONMENT** (code is done and verified locally/in staging;
needs a real server / domain / TLS / cloud or platform credentials that were
never supplied) · **NOT_APPLICABLE**.

Reviewed 2026-08-31. Code is the source of truth — see `backend/app/ops/`.

## 1. Data-loss prevention  (priority 1)
| Item | Status | Evidence / gap |
|---|---|---|
| Automated DB backup (`pg_dump -Fc`) | READY | `app/ops/backup.py::run_backup("full")`; sha256 + `BackupManifest`; Celery beat `ops-daily-backup` (24h). Verified: 1.2 MB `.dump`, valid checksum. |
| Backup verification (`pg_restore --list` + checksum) | READY | `verify_backup()` → status `VERIFIED` / `FAILED`; tampered-file test in `tests/ops/test_backup_restore.py`. |
| Restore rehearsal into a **separate** DB | READY | `restore_to(backup_id, "acf_restore_test")` refuses the source DB, DROP/CREATE target, `pg_restore --clean --if-exists`, re-checks `alembic_version` + table counts. Round-trip test passes; marker row survives. |
| Storage/asset backup | READY | `run_backup("storage")` tars `CRITICAL`+`REGENERATABLE` assets; manifest recorded. |
| Storage integrity scan (missing / corrupted) | READY | `storage_integrity.py::scan_assets()`; flags `MISSING_ASSET` / `CORRUPTED`, raises HIGH alert; test covers both. |
| Off-site / object-storage copy (S3) | NEEDS_PRODUCTION_ENVIRONMENT | `backup_destination` setting has an `s3` slot; no bucket/credentials supplied → only `local` is exercised. Backups land on the app volume; a real deploy must mount durable storage and/or push to S3. |
| PITR / WAL archiving | PARTIAL | Design target RPO ≤ 24 h from daily `pg_dump`; continuous WAL archiving (pgBackRest / `archive_command`) is documented in `DISASTER_RECOVERY.md` but not wired — needs a prod PG host. |
| DB constraints against silent loss | READY | Alembic `0006` adds unique indexes: `publish_jobs.idempotency_key`, `analytics_snapshots (publication_id, window_label)`, `publications.publish_job_id`, plus `job_leases` `uq_active_lease`. |

## 2. Duplicate-post prevention  (priority 2)
| Item | Status | Evidence / gap |
|---|---|---|
| Idempotent publish jobs | READY | Phase 2 `idempotency_key` + Phase 5 partial-unique index. |
| Job lease / single-execution guard | READY | `worker_registry.acquire_lease(job_kind, job_id)` — DB unique `(job_kind, job_id, released)`; second worker gets `None`. Test: `tests/ops/test_recovery.py`. |
| Webhook replay protection | READY | `publishing/webhooks.py` — a second `WEBHOOK_<state>` event for the same job returns `duplicate: true` without re-transitioning. Signed-replay test passes. |
| Stuck-job reclaim (no double-run after crash) | READY | `scan_stuck_jobs()` releases only expired leases; Celery `worker_shutdown` releases held leases as `RECOVERED`. Beat `ops-stuck-job-scan` every 120 s. |
| Emergency stop never touches in-flight remote uploads | READY | Phase 4 rule retained; `emergency.py` holds READY/SCHEDULED/QUEUED only. |

## 3. Secret-leak prevention  (priority 3)
| Item | Status | Evidence / gap |
|---|---|---|
| No hard-coded secrets in the repo | READY | `scripts/security/scan_secrets.py` — 10 rules, tight allowlist, runs clean; test plants a `ghp_` PAT and it is caught. |
| `.gitignore` blocks `.env` / keys / token dumps / `deploy/*.env` | READY | updated this phase. `.env.example` has **names only**. |
| Log + exception redaction (nested JSON, value-shaped) | READY | `ops/redaction.py` — key regex + value patterns (Bearer, `sk-`, `ghp_`, `ya29.`, `AKIA`, JWT, Fernet, DSN-with-password); `SecretRedactionFilter` on the root logger. `/api/ops/_debug/boom` returns a 500 whose body is scrubbed — test asserts no `gAAAAAB` / bearer literal leaks. |
| Encryption key separate from DB, versioned/rotatable | READY | `ACF_MASTER_KEY` (env / Docker secret), never stored; `RUNBOOK.md` §secret-rotation covers re-encrypt. Phase 2 `TokenManager` supports key id. |
| Env validation blocks unsafe production boot | READY | `ops/env.py::validate_environment()` — raises in prod on missing `SECRET_KEY`/`ACF_MASTER_KEY`, `CORS=*`, `TRUSTED_HOSTS=*`, localhost OAuth callback. Called at `app/main.py` import. |
| Docker secrets support | READY (code) / NEEDS_PRODUCTION_ENVIRONMENT (infra) | `ops/secrets.py::DockerSecretManager` reads `/run/secrets/<key>`. Compose `secrets:` blocks are the operator's to add with real material. |
| Transport security (HTTPS/HSTS) | NEEDS_PRODUCTION_ENVIRONMENT | HSTS header emitted when `APP_ENV=production`; TLS termination is the optional Caddy profile — needs a real domain + ACME. |

## 4. Uncontrolled-cost prevention  (priority 4)
| Item | Status | Evidence / gap |
|---|---|---|
| HARD budgets (daily/monthly, LLM+media+publish+autopilot) | READY | Phase 4 `enforce_hard_rules`, AI-immutable. |
| Cost-anomaly detector | READY | `ops/cost_anomaly.py` — rolling median × `COST_ANOMALY_FACTOR`, per campaign / provider-daily / LLM-token-surge → HIGH/WARNING alert. Test: spike detected. |
| Circuit breaker per provider (stops burning $ on a failing API) | READY | `ops/circuit_breaker.py` CLOSED/OPEN/HALF_OPEN; opens after `PROVIDER_BREAKER_THRESHOLD`, fast-fails for `PROVIDER_BREAKER_COOLDOWN_S`. |
| Queue backpressure halts new production | READY | `queue_backpressure.py` NORMAL/SLOW/HOLD wired into the autopilot production guard (`controller.py` → HOLD `stage="backpressure"`). |
| Rate limiting | READY | `ops/rate_limit.py` token bucket per (route class, client) → 429 + Retry-After. |

## 5. Service recovery  (priority 5)
| Item | Status | Evidence / gap |
|---|---|---|
| `/health/live` `/health/ready` `/health/dependencies` | READY | `routes_ops.py`; readiness 503 when DB/Redis/storage down or maintenance mode. DB-down / Redis-down tests flip readiness, not liveness. |
| Deep provider health probe (cached) | READY | `health.deep_health(force)` — 60 s cache. |
| Runtime flags survive restart (`EMERGENCY_STOP` / `SAFE_MODE` / `MAINTENANCE_MODE`) | READY | `runtime_flags.py` → `RuntimeSetting` row + `AuditEntry`; test clears the in-process cache and the flag still reads back. |
| DLQ + non-retryable guard | READY | `ops/dlq.py` — AUTH/POLICY/BUDGET/DUPLICATE never auto-retry; `dead_letters` table; API retry/resolve. |
| Worker heartbeat registry (STALE/DEAD) | READY | `worker_registry.worker_states()`; Celery signal handlers register/heartbeat/shutdown. |
| Docker restart policy + healthcheck | READY (code) | `Dockerfile` HEALTHCHECK on `/health/live`; `docker-compose.prod.yml` `restart: unless-stopped` + per-service healthcheck via base compose. Not run under a real orchestrator here. |
| Auto-scaling / multi-node | NOT_APPLICABLE (this phase) | Single-node compose. Worker queue split (`worker` / `worker-media` / `worker-analytics` / `worker-autopilot`) is in the prod overlay. |

## 6. Observability  (priority 6)
| Item | Status | Evidence / gap |
|---|---|---|
| Structured JSON logs + correlation id | READY | `ops/logging_config.py`; `OpsMiddleware` sets a per-request id (honours `x-correlation-id`), included in the 500 body. |
| Prometheus-text `/metrics` (no external dep) | READY | `ops/metrics.py` — counters/gauges/histograms, HTTP request totals + latency + 5xx, live DB-pool + Redis-queue gauges. Real exposure verified by `tests/ops`. |
| Ops dashboard (`/api/ops/status`) + frontend `/admin` | READY | health, workers, queues, flags, backups, open alerts, DLQ count; `frontend/app/admin/page.tsx` (`next build` clean) with dangerous-action confirms. |
| Deduplicated alerts + notifier interface | READY | `ops/alerts.py` — fingerprint + per-severity cooldown; `DashboardNotifier` default; `register_notifier()` for email/Slack/PagerDuty. |
| External alert delivery (email/Slack/PagerDuty) | NEEDS_PRODUCTION_ENVIRONMENT | Interface only; no channel credentials supplied. |
| OpenTelemetry traces | PARTIAL (opt-in stub) | `OTEL_ENABLED` flag exists and is a documented no-op until an OTLP endpoint + package are added. |
| Sentry error tracking | PARTIAL (opt-in stub) | `SENTRY_DSN` slot; no DSN supplied. |
| Log aggregation (Loki/ELK) | NEEDS_PRODUCTION_ENVIRONMENT | JSON logs go to stdout; shipping is an operator concern (optional Loki profile documented). |

## 7. Security hardening  (priority 7)
| Item | Status | Evidence / gap |
|---|---|---|
| SSRF egress filter | READY | `ops/ssrf.py` — blocks non-http(s), localhost, `.internal`, metadata IPs, DNS-resolved private/loopback/link-local/reserved; `SSRF_ALLOW_HOSTS` escape hatch. Parametrized tests. |
| Upload validation (magic bytes, size, traversal, safe name) | READY | `ops/upload_security.py`; `validate_upload()` rejects sniff/declared mismatch + oversize; `safe_filename()` = uuid + sanitized ext. |
| FFmpeg never `shell=True` | READY | argument lists throughout `app/media/`; no change needed, re-audited. |
| Security headers (nosniff, DENY, no-referrer, HSTS in prod) | READY | `OpsMiddleware`; test asserts presence. |
| Request size cap (413) | READY | `OpsMiddleware` on `content-length` > `MAX_REQUEST_BYTES`. |
| Docs/OpenAPI disabled in prod | READY | `main.py` — `docs_url=None` when `is_production`. |
| Non-root container | READY | `Dockerfile` `USER appuser` (uid 10001), `no-new-privileges`. |
| Append-only audit log | READY | `audit_log` table; "application code never updates/deletes these rows"; flag changes + secret-rotation events recorded. |
| Authn/authz on `/api/ops/*` | PARTIAL | Actions require explicit `confirm=true` and are audit-logged, but the ops router has no auth layer of its own — it inherits whatever fronts the deployment (reverse-proxy auth / network isolation). Documented in `DEPLOYMENT_CHECKLIST.md`. |
| WAF / DDoS protection | NEEDS_PRODUCTION_ENVIRONMENT | Out of app scope; in-app rate limiting only. |

## Go-live blockers (must be cleared by the operator)
1. Provision a real Postgres with WAL archiving + durable/off-site backup storage (S3).
2. Supply `SECRET_KEY`, `ACF_MASTER_KEY`, DB/Redis passwords as Docker secrets or a real secret store.
3. Real domain + TLS (enable the Caddy `proxy` profile or terminate TLS upstream).
4. Set `CORS_ALLOW_ORIGINS` / `TRUSTED_HOSTS` to real hostnames (boot refuses `*`).
5. Put an auth boundary in front of `/api/ops/*` and `/admin`.
6. Wire at least one real alert channel via `register_notifier()`.
7. Supply real platform/provider credentials (still MOCK/DRY_RUN otherwise — unchanged from Phases 2–4).
