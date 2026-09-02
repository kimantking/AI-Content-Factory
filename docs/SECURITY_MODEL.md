# SECURITY MODEL (Phase 6)

Authentication, RBAC, and tenant-scope authorization for the multi-brand /
multi-channel platform. Closes the Phase 5 known limitation ("`/api/ops/*` and
`/admin` have no built-in auth"). Code: `backend/app/auth/`, `backend/app/mb/scope.py`.

## 1. Identity

- **Local users** with a stdlib-pbkdf2 password hash **and/or** a hashed API key
  (`app/auth/service.py`). No SaaS auth-provider dependency. Format: `acf_<40 hex>`;
  stored as an HMAC-SHA256 keyed by `SECRET_KEY` (lookup by hash, no plaintext).
- **External identity** can be added later behind an `IdentityProvider` seam
  without touching callers — not built this phase.
- **Bootstrap**: `BOOTSTRAP_ADMIN_EMAIL` + `BOOTSTRAP_ADMIN_KEY` env vars create a
  system-admin with a fixed key on first boot (local/first-run convenience;
  production should rotate via `POST /api/admin/users/{id}/api-key`).

## 2. Where auth is enforced

`OpsMiddleware` (in `app/main.py`) 401s any request to
`/api/ops/*`, `/api/admin/*`, `/admin` **when** `APP_ENV in (production, staging)`
**or** `AUTH_ENFORCE=true`. Health (`/health/*`) and `/metrics` stay open for
scrapers. A valid `X-Api-Key` / `Authorization: Bearer` is honoured in every
environment. In `development` / `test` the gate is **off** so the existing suite
runs unchanged, but an anonymous request there gets a synthetic
`is_system_admin` context (dev only).

All `/api/workspaces`, `/api/brands`, `/api/channels`, `/api/portfolio`,
`/api/monetization` endpoints run their own `current_user` + scope checks
regardless of the middleware gate.

## 3. RBAC

Roles (highest first): **OWNER > ADMIN > PUBLISHER > EDITOR > ANALYST > VIEWER**.
Capabilities map to a minimum role (`app/auth/context.py::CAPABILITY_MIN_ROLE`):

| Capability | Min role |
|---|---|
| `workspace.manage`, `member.manage` | OWNER |
| `budget.write`, `brand.write`, `channel.write`, `autopilot.write`, `sponsor.write`, `affiliate.write` | ADMIN |
| `content.write`, `campaign.create` | EDITOR |
| `publish.approve`, `publish.run` | PUBLISHER |
| `analytics.read`, `revenue.read` | ANALYST |
| `read` | VIEWER |

A **system admin** (`User.is_system_admin`) bypasses role checks and can see
across workspaces. System admin ≠ workspace owner (§73).

## 4. Tenant-scope authorization (no IDOR)

Every workspace-scoped resource is fetched **and checked** via
`app/mb/scope.py`: `get_workspace / get_brand / get_channel` raise **403** unless
the row's `workspace_id` is one the caller is a member of. `scoped_query()`
pre-filters list endpoints to the caller's memberships. Knowing an id is never
enough.

Verified by `tests/mb/test_isolation.py`:
- workspace A owner reading workspace B's brand / channel / workspace → **403**
- `GET /api/channels` returns only the caller's workspace's channels
- `POST /api/portfolio/route` with a foreign `workspace_id` → **403**
- system admin sees both workspaces

## 5. Credential-scope isolation (§70–§71)

`token_manager.assert_credential_scope(account, expected_workspace, expected_brand,
expected_platform)` raises `PublishError(AUTH_REVOKED)` if a `PlatformAccount`'s
`workspace_id` / `brand_id` / `platform` doesn't match what the caller expects.
`ensure_valid(...)` calls it before returning a token. Brand A's Instagram token
can never be handed to Brand B's publisher. Legacy accounts with NULL scope are
allowed only when no expectation is passed (opt-in migration).

## 6. Budget as a safety control

Hierarchical **hard** limits (Workspace ⊇ Brand ⊇ Channel ⊇ Campaign) with a
**transactional reservation** (`app/mb/budget.py`): the reserve check + insert
run inside one transaction that row-locks the day's rows for the scope, so
concurrent workers cannot collectively exceed a hard limit. Proven by
`tests/mb/test_budget.py::test_concurrent_reservations_cannot_exceed_hard_limit`
(two threads, one succeeds, one blocked).

## 7. Cache / queue tenant context (§86–§87)

- Cache keys for tenant-specific data include `workspace_id` where relevant
  (media asset cache already keys by content hash; memory/strategy caches are
  scoped by the retriever filter — §85).
- Worker jobs carry `workspace_id / brand_id / channel_id` in the campaign row
  (`campaigns.workspace_id` etc., added NULLABLE in `0007`); the pipeline reads
  the scope from the campaign. **Status: campaign rows carry the columns; a
  strict job-context validator is DESIGN_ONLY this phase.**

## 8. Audit

`audit_log` (Phase 5, append-only) records brand/channel creation, budget
changes, autopilot-mode changes, account connect, sponsor deals, channel pause,
reposition recommendations. **Status: the table and helper exist; wiring every
Phase-6 mutation to it is partial — DESIGN_ONLY for full coverage.**

## 9. URL Learning (Cross-Phase Intelligence Upgrade)

Code: `app/intel/url_security.py`, `intel/injection.py`, `intel/fetch.py`. Full
detail in `URL_LEARNING_ENGINE.md`.

- **Untrusted external content.** Everything fetched from a URL is
  `UNTRUSTED_EXTERNAL_CONTENT`. Page text such as "ignore previous instructions",
  "run this command", "install this package", "delete database", "reveal API
  key", "change system prompt" (EN + KO) is **data, never an instruction**.
  `injection.scan` classifies, `injection.sanitize` blanks the matched spans, and
  `injection.wrap_untrusted` quotes the remainder before any LLM sees it. Nothing
  from a reference is ever executed. A flagged reference is recorded
  (`injection_flag`, `injection_detail`) and quality-penalised.
- **SSRF.** Reuses the Phase 5 guard (`ops.ssrf`). Blocks localhost,
  `127.0.0.0/8`, private / link-local / reserved IPs, metadata endpoints,
  `*.internal` / `*.local`, and non-http(s) schemes (`file://`, `gopher://`,
  `ftp://`, `ws(s)://`, `redis://`, `postgres://`). Every redirect hop is
  re-validated (`fetch.py` + the mock client both do per-hop checks). Production
  runs the full DNS-rebinding check (resolves every A/AAAA record); non-production
  skips a blocking DNS lookup for unresolved hostnames (they cannot reach an
  internal service, and the fetch fails safely).
- **Browser adapter.** `BrowserFetchAdapter` is off by default
  (`browser_fetch_enabled`); the stub raises `AdapterUnavailable`. No adapter may
  bypass CAPTCHA / paywall / login / DRM / anti-bot.
- **Rights separation.** A page used as a research reference is not a licence to
  reuse its images/video — those go through the Phase 7 RightsLedger separately
  (`ReferenceSource.rights_status` defaults to `RESEARCH_REFERENCE`).
- **Tenant isolation.** References / datasets / blueprints / skills / recipes all
  carry `workspace_id / brand_id / channel_id`; reads and the dedup corpus are
  workspace-scoped — Brand A's learning data never reaches Brand B.
- **Hard guards.** `max_learning_items_per_job`, `max_daily_learning_items`,
  `max_learning_cost_usd`, `max_reference_bytes`, `learning_deep_analysis_top_k`
  — exceeding a limit raises `LearningGuardError` (HTTP 429). No unbounded
  crawling; the watchlist is opt-in only.

## 10. Known limitations / NEEDS_PRODUCTION_ENVIRONMENT

- No password-login UI or session cookies — API-key auth only (a login flow is a
  frontend + `POST /api/auth/login` follow-up).
- No rate-limit-per-user (the Phase-5 limiter is per-client-IP).
- Strict worker-job tenant-context validation and full audit-log coverage of
  Phase-6 mutations are DESIGN_ONLY.
- Real external IdP (OIDC/SAML) is a seam, not implemented.
