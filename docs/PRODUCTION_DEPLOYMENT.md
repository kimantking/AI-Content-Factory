# Production Deployment (Phase 10 §17-§19)

Extends `docs/RUNBOOK.md` / `docs/DEPLOYMENT_CHECKLIST.md` /
`docs/PRODUCTION_READINESS.md`.

## Docker (prod overlay)
`docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file deploy/prod.env`
* **no dev source bind mounts** (image is a clean build), `restart: unless-stopped`,
  health checks on backend/worker, resource limits, private network for DB+Redis
  (**not published to the host**), secrets via env file / docker secrets, not baked
  into the image.
* `backend` runs `alembic upgrade head` on boot; wait for `/health/ready`.

## Deploy sequence (§18)
`Backup → Migration (additive-only, single head 0011) → App rollout → Health
validation (/health/ready + /api/ops/config-check + /api/ops/deep-health)`.
Destructive DDL is avoided. **Rollback:** deploy the previous image tag; the DB
schema is forward-compatible additive, so an app rollback needs no down-migration
in the normal case — if a migration must be reverted, `alembic downgrade -1`
against a restored backup.

## Domain / TLS (§19)
Real domain + reverse proxy (Caddy profile) + HTTPS + security headers required
before calling it production. HTTP-only is **not** production-ready.
Without a domain: `DOMAIN_TLS = NEEDS_PRODUCTION_ENVIRONMENT`.

## Storage (§20)
Local + S3-compatible adapter. Asset categories: temporary / cache / reference /
final / published. Local/staging backup+restore verified
(`tests/ops/test_backup_restore.py`). Off-site target + WAL/PITR:
`NEEDS_PRODUCTION_ENVIRONMENT`.
