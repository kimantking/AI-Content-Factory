# Security Checklist (Phase 10 §16, §48, §75, §91)

Backend is the final authority — hiding a frontend button is not security.

## AuthZ
- [x] Auth + API key / session; `AuthContext` per request
- [x] RBAC capability gates (`ctx.require(...)`), Viewer cannot do protected writes — `tests/mb`, `tests/phase9`
- [x] Tenant isolation + IDOR guard (`ctx.assert_workspace`) — `tests/mb/test_isolation.py`, `tests/phase9`, `tests/phase10/test_support_snapshot.py`
- [x] AI Support Snapshot is workspace-scoped; admin-only infra detail; other-tenant data = 0

## Input / network
- [x] SSRF guard on URL learning (localhost / private IP / metadata / file:// / redirect-to-private) — `tests/intel`, `tests/phase9/test_security_load.py`
- [x] Prompt-injection detector + sanitiser + untrusted-wrap; batch poison → 0 execution
- [x] Internal Ollama (`localhost:11434`) reachable via the app's own client while user-fetch of localhost is blocked
- [ ] CORS / trusted hosts scoped in production (validator enforces)
- [ ] Upload safety (size / type) — reviewed per deployment
- [x] Security headers via the prod reverse-proxy profile

## Gates (unbypassable)
- [x] Governance gate (BLOCK / FIX_REQUIRED / HUMAN_REVIEW never PUBLISHED; fails safe)
- [x] Rights ledger expiry re-checked at publish time
- [x] Budget hard limit (workspace/brand/channel/campaign), transactional under concurrency
- [x] Publisher gate: platform selection + credential + governance re-checked right before the remote call
- [x] Kill switches: GLOBAL_PUBLISH_PAUSE, GLOBAL_PAID_PROVIDER_PAUSE, EMERGENCY_STOP

## Secrets
- [x] `app/ops/redaction.py` — key + value patterns (Bearer, gh?_, sk-/sk-ant-, Stripe, ya29., AKIA, xox*, JWT, Fernet, DSN-with-password); `SecretRedactionFilter` on logs
- [x] Support Snapshot (JSON + copy text + screenshot) contains 0 keys / tokens / passwords / Authorization headers / other-tenant data — `tests/phase10/test_support_snapshot.py`
- [x] `scripts/security/scan_secrets.py` clean on the repo (CI test plants a PAT and it is caught)
- [x] Token encryption at rest (Fernet, `ACF_MASTER_KEY`)
