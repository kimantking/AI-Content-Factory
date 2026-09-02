# Production Checklist (Phase 10)

Run `GET /api/ops/config-check` — `production_ready` must be `true`, `blocking_problems` empty.

## Config
- [ ] `APP_ENV=production`, `DEBUG=false`
- [ ] `SECRET_KEY`, `ACF_MASTER_KEY` set (strong)
- [ ] `MOCK_MODE=false`, `llm_is_mock=false` — `silent_mock_fallback_in_prod=false`
- [ ] `CORS_ALLOW_ORIGINS` / `TRUSTED_HOSTS` scoped (not `*`)
- [ ] `PUBLIC_BASE_URL` / `OAUTH_CALLBACK_BASE_URL` = `https://…`
- [ ] `campaign_budget_usd` > 0; brand/workspace hard budgets set
- [ ] no duplicate keys in `.env`

## Providers
- [ ] `ANTHROPIC_API_KEY` (+ verified pricing) — or LOCAL_ONLY accepted
- [ ] `TAVILY_API_KEY` — or research quality accepted with mock/degraded
- [ ] Ollama reachable + `gemma3:4b` present (`GET /api/local-ai/status`)
- [ ] media providers: mock-only acknowledged (NEEDS_CREDENTIALS)

## Security
- [ ] Auth + RBAC + tenant isolation (backend-enforced, not button-hiding)
- [ ] SSRF / prompt-injection guards on (URL learning)
- [ ] Publisher / Budget / Governance gates enforced
- [ ] Secret scan clean (`scripts/security/scan_secrets.py`)
- [ ] `SECURITY_CHECKLIST.md` items reviewed

## Deploy
- [ ] Docker prod overlay: no bind mounts, health checks, resource limits, DB/Redis not host-exposed
- [ ] Backup taken; migration head = `0011_medium_repair` (single); rollback plan noted
- [ ] `/health/ready` = ready; `/api/ops/deep-health` OK

## Operations
- [ ] Kill switches tested: GLOBAL_PUBLISH_PAUSE, GLOBAL_PAID_PROVIDER_PAUSE, EMERGENCY_STOP
- [ ] Backup schedule + off-site target (or accept NEEDS_PRODUCTION_ENVIRONMENT)
- [ ] Monitoring / alert delivery wired (or accept NEEDS_PRODUCTION_ENVIRONMENT)
- [ ] `OPERATIONS_RUNBOOK.md` + `INCIDENT_RESPONSE.md` on hand
- [ ] First pilot planned: 1 content × 1 platform, human-approved
