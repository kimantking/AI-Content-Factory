# Production Configuration (Phase 10 §2-§3)

Environments: `development` · `test` · `staging` · `production` (`APP_ENV`).
Validator: `GET /api/ops/config-check` → `app/ops/config_check.py`
(delegates hard prod checks to `app/ops/env.py::validate_environment`).

## Production requires (hard — `production_ready: false` otherwise)
| Setting | Rule |
|---|---|
| `SECRET_KEY` | set, ≥ 16 chars |
| `ACF_MASTER_KEY` | set (token encryption) |
| `DEBUG` | false |
| `MOCK_MODE` / `llm_is_mock` | false — production must NOT silently run on mock (`silent_mock_fallback_in_prod` flags it) |
| `CORS_ALLOW_ORIGINS` | not `*` |
| `OAUTH_CALLBACK_BASE_URL` / `PUBLIC_BASE_URL` | `https://…`, not localhost |
| `campaign_budget_usd` | > 0 (a per-campaign hard cap) |

## Capability status vocabulary
`READY · DEGRADED · NOT_CONFIGURED · NEEDS_CREDENTIALS · NEEDS_PRODUCTION_ENVIRONMENT · MISCONFIGURED`

Reported per capability: `APP_ENV`, `DATABASE_URL`, `REDIS_URL`, `PUBLIC_BASE_URL`,
`OLLAMA`, `ALLOW_CLOUD_FALLBACK`, `MODEL_ROUTER`, `ANTHROPIC`, `TAVILY_SEARCH`,
`MEDIA_PROVIDERS`, `BUDGETS`, `WORKER_CONCURRENCY`, `OFF_SITE_BACKUP`, `WAL_PITR`,
`EXTERNAL_MONITORING`, `DOMAIN_TLS`.

## Key env variables (see `backend/.env.example` for the full list)
`APP_ENV`, `SECRET_KEY`, `ACF_MASTER_KEY`, `PUBLIC_BASE_URL`, `DATABASE_URL`,
`SYNC_DATABASE_URL`, `REDIS_URL`, `STORAGE_ROOT`/`OUTPUT_ROOT`,
`OLLAMA_ENABLED`, `OLLAMA_BASE_URL`, `OLLAMA_DEFAULT_MODEL`, `ALLOW_CLOUD_FALLBACK`,
`MODEL_ROUTER_ENABLED`, `QUALITY_PRESET`, `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`,
`CAMPAIGN_BUDGET_USD` / `DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD`,
`CORS_ALLOW_ORIGINS`, `TRUSTED_HOSTS`, `OAUTH_CALLBACK_BASE_URL`,
`LOCAL_MODEL_MAX_CONCURRENCY`, `WEBHOOK_SECRET`, `DRY_RUN`, `PLATFORM_CLIENT`.
The validator flags duplicate keys in `.env`.
