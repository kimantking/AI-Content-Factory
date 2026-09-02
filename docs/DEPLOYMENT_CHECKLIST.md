# DEPLOYMENT CHECKLIST

Phase 5. Run top-to-bottom for a first production deploy; the **Every deploy**
section is the recurring subset. `[ ]` = operator action.

## 0. Prerequisites (one-time)
- [ ] Host with Docker + Compose v2, outbound HTTPS, a durable data disk for `pgdata` + `backups`.
- [ ] DNS A/AAAA record for the app domain.
- [ ] A secret store or at least a locked-down `deploy/prod.env` (git-ignored).
- [ ] Off-site / object-storage bucket for backup copies (S3 or equivalent) with versioning + object lock.
- [ ] Real platform/provider credentials if live posting is intended (else it stays MOCK / DRY_RUN — same as Phases 2–4).

## 1. Secrets & config
- [ ] `deploy/prod.env` created from `.env.example` — **names only there; values here**.
- [ ] `APP_ENV=production`.
- [ ] `SECRET_KEY` set (32+ random bytes). Boot **fails** if missing in prod.
- [ ] `ACF_MASTER_KEY` set, stored **separately** from the DB, with its own vault backup.
- [ ] `POSTGRES_PASSWORD`, `REDIS_PASSWORD` set (not `acf`/blank).
- [ ] `CORS_ALLOW_ORIGINS` = real origin(s), **not** `*`. Boot fails on `*` in prod.
- [ ] `TRUSTED_HOSTS` = real hostname(s), **not** `*`.
- [ ] `PUBLIC_BASE_URL`, `FRONTEND_URL`, `OAUTH_CALLBACK_BASE_URL` = real `https://` URLs (no `localhost`).
- [ ] `BACKUP_DIR` points at the durable disk; `BACKUP_RETENTION_DAYS` agreed.
- [ ] `BACKUP_ENCRYPTION_KEY` set if backups must be encrypted at rest.
- [ ] Prefer Docker `secrets:` over env for `SECRET_KEY` / `ACF_MASTER_KEY` / passwords — `ops/secrets.py::DockerSecretManager` reads `/run/secrets/<key>`.
- [ ] `git status` clean; `python scripts/security/scan_secrets.py` exits 0.
- [ ] Confirm `.env`, `deploy/*.env`, `*.key`, `*.pem`, `credentials*.json` are git-ignored.

## 2. Network / TLS
- [ ] TLS terminated — either enable the Caddy profile (`--profile proxy`, set `PROXY_DOMAIN` + `ACME_EMAIL`) or terminate upstream (ALB / nginx).
- [ ] Only 80/443 exposed publicly. Postgres (5432) and Redis (6379) **not** published — the prod overlay sets `ports: []` for both.
- [ ] Auth boundary in front of `/api/ops/*` and `/admin` (proxy basic-auth, SSO, or network isolation) — the ops router has no built-in auth.
- [ ] `/docs` + `/openapi.json` are disabled automatically in prod (`is_production`); confirm they 404.

## 3. Database
- [ ] Managed Postgres or a hardened container with a mounted volume.
- [ ] WAL archiving / PITR configured if RPO < 24 h is required (see `DISASTER_RECOVERY.md`).
- [ ] `alembic upgrade head` succeeds (runs on `backend` boot) → head `0006_production`.
- [ ] `statement_timeout` / pool settings active — `app/db/base.py` applies them when `APP_ENV=production`.
- [ ] `acf_restore_test` DB name is free (restore rehearsals use it).

## 4. Backups (verify before, not after, go-live)
- [ ] `POST /api/ops/backups/run {"kind":"full"}` → succeeds.
- [ ] `POST /api/ops/backups/<id>/verify` → `VERIFIED`.
- [ ] `restore_to('<id>','acf_restore_test')` → `RESTORE_TESTED`, `migration_revision` `0006*`.
- [ ] `ops-daily-backup` beat entry present (`$COMPOSE exec worker celery -A app.celery_app.celery_app inspect scheduled` or check `celery_app.py`).
- [ ] Off-site copy job configured (cron/rclone/S3 sync of `BACKUP_DIR`).
- [ ] `deploy/prod.env` + `ACF_MASTER_KEY` backed up to the vault (they are **not** in DB backups).

## 5. Workers & queues
- [ ] `worker` (core+publish+beat), `worker-media`, `worker-analytics`, `worker-autopilot` all `Up`.
- [ ] `/api/ops/workers` lists them `HEALTHY` within ~30 s.
- [ ] `/api/ops/queues` → `NORMAL`.
- [ ] `ops-stuck-job-scan` (120 s) and `ops-heartbeat` (30 s) beat entries active.

## 6. Observability
- [ ] `/metrics` returns Prometheus text with `acf_http_requests_total`.
- [ ] Scrape configured (Prometheus) or accept pull-only.
- [ ] JSON logs reaching your log sink (stdout → Docker → shipper).
- [ ] At least one real notifier registered via `register_notifier()` (email/Slack/PagerDuty) — default is dashboard-only.
- [ ] Optional: `OTEL_ENABLED` + OTLP endpoint; `SENTRY_DSN`.
- [ ] Alert routing for severity `HIGH`/`CRITICAL` tested end to end.

## 7. Security review
- [ ] `validate_environment()` passes at boot with no warnings (check `backend` logs).
- [ ] `SSRF_ENFORCE=true`; `SSRF_ALLOW_HOSTS` only what's genuinely needed.
- [ ] `RATE_LIMIT_ENABLED=true`; limits sized for real traffic (`ops/rate_limit.py::_LIMITS`).
- [ ] `MAX_REQUEST_BYTES` / `MAX_UPLOAD_BYTES` sane for the deployment.
- [ ] Container runs as non-root (`USER appuser`), `no-new-privileges:true`.
- [ ] Security headers present on a real response (`curl -I` → nosniff / DENY / HSTS).
- [ ] `audit_log` writable, never updated/deleted by app code (append-only by design).
- [ ] Secret redaction spot-check: trigger a handled error in staging, confirm the log line is scrubbed.

## 8. App behaviour
- [ ] `DRY_RUN=true` for the first run even in production; flip to live only after a clean preflight.
- [ ] HARD budgets (`daily_hard_budget` / `monthly_hard_budget` / `daily_post_limit`) set to real numbers via `/api/autopilot/config` as `actor=user`.
- [ ] Autopilot mode starts at `SUGGEST_ONLY` (or `OFF`); escalate deliberately.
- [ ] Blocked topics/keywords + `min_compliance_score` reviewed.
- [ ] AI-content disclosure still enforced (unchanged; never stripped).

## 9. Smoke test (post-deploy)
- [ ] `curl -fsS https://<domain>/health/ready` → `{"ready": true}`.
- [ ] `/health/dependencies` → DB / Redis / storage `OK`.
- [ ] `/api/ops/status` → workers healthy, no open `CRITICAL` alerts, `dlq_open` = 0.
- [ ] `/admin` loads, shows green health.
- [ ] Create one MOCK campaign end-to-end (or SHADOW autopilot run) → no errors.
- [ ] Watch `acf_http_5xx_total` for 15 min → flat.

## 10. Rollback readiness
- [ ] Pre-deploy full backup taken and `VERIFIED` (step 4).
- [ ] Previous image tag / git tag known.
- [ ] Rollback steps rehearsed (`RUNBOOK.md` → *Rollback*), incl. the "restore backup if a migration ran" rule.

---

## Every deploy (recurring subset)
1. [ ] `POST /api/ops/backups/run {"kind":"full"}` → `verify` → `VERIFIED`.
2. [ ] `scan_secrets.py` exits 0; `git status` clean.
3. [ ] Maintenance mode ON.
4. [ ] `$COMPOSE build backend worker` ; `$COMPOSE up -d` (migrations auto-run).
5. [ ] `/health/ready` true ; `/api/ops/status` clean.
6. [ ] Maintenance mode OFF.
7. [ ] Watch `/metrics` 5xx + `/api/ops/alerts` for 15 min.

## Known limitations at go-live (from PRODUCTION_READINESS.md)
- No real production server/domain/TLS/cloud/SNS credentials were provided to this project — items depending on them are **CODE READY / LOCAL-STAGING VERIFIED / NEEDS_PRODUCTION_ENVIRONMENT**, not verified in a live environment.
- Off-site/S3 backup, WAL/PITR, external alert channels, OTel/Sentry export, and log aggregation are code-ready or interface-only and must be wired by the operator.
- `/api/ops/*` has no native auth — it relies on the deployment's front door.
