# Monitoring & Alerts (Phase 10 §21, §41)

## Health
`GET /health/live`, `/health/ready`, `/health/dependencies`,
`GET /api/ops/status`, `/api/ops/deep-health`, `GET /metrics` (Prometheus text).
Covers: backend, DB, Redis, workers, scheduler, storage, FFmpeg, Ollama,
providers, publishers, queue backpressure.

The **AI Support Snapshot** (`/support`, `GET /api/support/snapshot`) is the
human-facing rollup of all of the above plus the current job / last error /
routing / cost.

## Structured logging
`app/ops/logging` — JSON logs with timestamp, level, service, and (where in
scope) request_id / campaign_id / job_id / workspace_id / provider / error_code /
error_class. `SecretRedactionFilter` scrubs every record.

## Error taxonomy → user action
`app/support/errors.py` normalises to `OLLAMA_UNAVAILABLE`,
`PROVIDER_RATE_LIMITED`, `VIDEO_PROVIDER_TIMEOUT`, `DB_CONNECTION_FAILED`,
`REDIS_UNAVAILABLE`, `RENDER_FFMPEG_FAILED`, `STORAGE_WRITE_FAILED`,
`PUBLISH_AUTH_EXPIRED`, `GOVERNANCE_BLOCKED`, `BUDGET_EXCEEDED`,
`PLATFORM_DISABLED`, `WORKER_STALLED`, … each with a one-line fix.

## Alerts
`app/ops` has dedup + a `DashboardNotifier` (in-app). Actionable alert types:
publish failed, review needed, budget warning, SNS auth expired, Ollama error,
worker error. **External delivery** (email / Slack / PagerDuty):
`NEEDS_PRODUCTION_ENVIRONMENT` — wire an `AlertChannel` and set its endpoint.

## Stall detection (§78)
`POST /api/ops/workers/scan-stuck` + lease expiry; job-type-specific thresholds
(render vs research), not a global 5-minute hardcode. Surfaced as
`WORKER_STALLED` in the snapshot.
