# PRODUCTION VERIFICATION MATRIX — Phase 1 ~ Phase 8

> Columns: **Code Ready** (implemented) · **Mock Verified** (passes with mock
> provider) · **Local Verified** (real local service) · **Production Verified**
> (real prod credential/environment) · **Missing Requirement** (what's needed to
> move right). Production Verified is **never** claimed from a mock pass.

## AI providers

| Provider | Code Ready | Mock Verified | Local Verified | Production Verified | Missing Requirement |
|---|:-:|:-:|:-:|:-:|---|
| LLM — Anthropic (`anthropic_llm.py`) | ✅ | ✅ | — | ❌ | `ANTHROPIC_API_KEY`; verified pricing (D10) |
| LLM — Ollama (`ollama_llm.py`) | ✅ | ✅ | **✅** (`gemma3:4b`, live JSON inference 2.3 s) | n/a (local) | — |
| Search — Tavily (`tavily_search.py`) | ✅ | ✅ | — | ❌ | `TAVILY_API_KEY` |
| Image / Video / TTS / Stock / Music | ✅ (abstraction) | ✅ | — | ❌ | real provider adapter + key; then non-MOCK media cost |
| Forced alignment — WhisperX | ⚠️ scaffold + working estimator fallback | ✅ (estimator) | — | ❌ | `whisperx` model install |
| Perceptual video — VMAF | ⚠️ adapter seam | — | — | ❌ | libvmaf / adapter impl (OPTIONAL) |

## Publishing platforms

| Platform | Code Ready | Mock Verified | Local | Production Verified | Missing Requirement |
|---|:-:|:-:|:-:|:-:|---|
| YouTube (Shorts/Long) | ✅ | ✅ | — | ❌ | OAuth client + Data API creds + channel |
| TikTok | ✅ | ✅ | — | ❌ | approved app + Content Posting API |
| Instagram (Reels/Feed/Carousel) | ✅ | ✅ | — | ❌ | FB/IG Graph app review + business account |
| Facebook (Reels) | ✅ | ✅ | — | ❌ | Graph app review + Page |
| Threads | ✅ | ✅ | — | ❌ | Threads API access |
| X (Post/Thread/Image/Video) | ✅ | ✅ | — | ❌ | paid API tier + keys |
| Pinterest (Image/Video Pin) | ✅ | ✅ | — | ❌ | app + token |
| LinkedIn (Text/Image/Video/Document) | ✅ | ✅ | — | ❌ | app + token |
| Naver Blog | ✅ (capability: MANUAL/LIMITED) | ✅ | — | ❌ | Naver credentials / manual flow |
| Naver Clip | ✅ (capability) | ✅ | — | ❌ | Naver credentials |

*All 10 have capability-registry entries with an honest status
(SUPPORTED/AUTH_REQUIRED/APP_REVIEW_REQUIRED/ACCOUNT_TYPE_REQUIRED/LIMITED/
MANUAL_ONLY/NOT_SUPPORTED). Publisher engine (idempotency/retry/schedule/reconcile/
DLQ/gate) is Code Ready + Mock Verified; no real remote publish has occurred.*

## Analytics / revenue sources

| Source | Code Ready | Mock Verified | Local | Production Verified | Missing Requirement |
|---|:-:|:-:|:-:|:-:|---|
| Platform analytics APIs (views/retention/…) | ✅ (capability-gated, null≠0) | ✅ | — | ❌ | per-platform analytics scopes |
| Ad / platform revenue | ✅ (actual vs estimate separated) | ✅ | — | ❌ | monetisation API access |
| Affiliate / sponsor revenue | ✅ (manual + guards) | ✅ | — | ❌ | operator data entry |

## Infrastructure / ops (Phase 5)

| Item | Code Ready | Local/Staging Verified | Production Verified | Missing Requirement |
|---|:-:|:-:|:-:|---|
| Docker + compose (prod profile, queue split) | ✅ | ✅ (`docker compose config`) | ❌ | prod host |
| Postgres + pgvector + Redis | ✅ | ✅ (local :5433 / :6379) | ❌ | managed instances |
| Backup → verify → restore | ✅ | ✅ (real pg_dump/restore round-trip) | ❌ | off-site / S3 target, WAL/PITR |
| Health / readiness / deep-health | ✅ | ✅ | ❌ | prod probes |
| Structured logging + secret redaction | ✅ | ✅ | ❌ | log aggregation |
| Rate limit / circuit breaker / DLQ / leases / worker registry | ✅ | ✅ (`tests/ops` 44) | ❌ | prod load |
| Alerts | ✅ (dedup + `DashboardNotifier`) | ✅ | ❌ | real channel (email/Slack/PagerDuty) |
| TLS / domain / reverse proxy | ✅ (Caddy profile) | — | ❌ | domain + cert |
| OTel / Sentry | ✅ (no-op seam) | — | ❌ | endpoint / DSN |
| Secret store | ✅ (`Env`/`DockerSecretManager`) | ✅ | ❌ | real vault + `SECRET_KEY`/`ACF_MASTER_KEY` |

## Governance (Phase 7)

| Item | Code Ready | Verified (deterministic/mock) | Production Verified | Missing Requirement |
|---|:-:|:-:|:-:|---|
| Rights ledger / manifest / lineage / expiry / attribution | ✅ | ✅ (`tests/governance` 46) | n/a (deterministic) | — |
| Originality (text/pHash/video-structure/cross-brand/vs-references) | ✅ | ✅ | n/a | heavy CV fingerprint = OPTIONAL |
| Platform policy registry + verification | ✅ | ✅ (FIXTURES + staleness + human-in-the-loop verify, `tests/governance/test_policy_verify` 6) | ❌ live *fetch* | AUDIT-P7-001 RESOLVED (review queue + attested `record_verification`). Live policy fetch stays LEGAL_REVIEW_REQUIRED / NEEDS_PRODUCTION_ENVIRONMENT |
| AI disclosure never-stripped | ✅ | ✅ | n/a | — |
| Publisher / Autopilot gate (hard BLOCK unbypassable) | ✅ | ✅ | n/a | — |

## Model Router / Local AI (Phase 8)

| Item | Code Ready | Mock/Local Verified | Wired to production agent path | Missing Requirement |
|---|:-:|:-:|:-:|---|
| Ollama provider | ✅ | ✅ **LOCAL_VERIFIED** | **✅** | AUDIT-P8-001 RESOLVED — `agents/nodes.py`/`media_nodes.py` route via `model_gateway`; a light agent task provably runs on `gemma3:4b` |
| Model Registry (health-probed) | ✅ | ✅ | **✅** (cost/benchmark/API **+ every agent LLM call**) | — |
| Model Router tiers / escalation / LOCAL_ONLY / budget-pressure | ✅ | ✅ (`tests/ai_router` 35 + `tests/agents/test_model_gateway` 15) | **✅** | AUDIT-P8-001 RESOLVED |
| Routing telemetry + performance memory + auto-tune | ✅ | ✅ (`test_autotune` 3) | **✅ from real agent runs** | AUDIT-P8-005 RESOLVED — `select()` prefers proven engines, min-sample guarded |
| Benchmark service | ✅ | ✅ (MOCK_VERIFIED; LOCAL_VERIFIED when run vs Ollama) | n/a | run benchmark against `gemma3:4b` for real per-task strength |
| Cost estimator | ✅ | ✅ (genuinely routes for LLM lines) | n/a | media prices UNKNOWN until real providers |
| PromptComposer (Base+Brand+Channel+Memory+Skills+Blueprints) | ✅ | ✅ (`test_composer` 5 + `test_prompt_composer_wiring` 11) | **✅ on the agent path** | AUDIT-P8-006 RESOLVED — merged before routing; lineage in `ModelRoutingEvent.prompt_lineage` |

## Content Library (Phase 8)

| Item | Code Ready | Verified | Missing Requirement |
|---|:-:|:-:|---|
| Discover ALL existing content (incl. legacy) | ✅ | ✅ (`tests/library` 18) | — |
| Real MP4 stream to browser | ✅ | ✅ | — |
| 12-tab detail (DB/API-backed) | ✅ | ✅ | — |
| Add-platform-later isolation | ✅ | ✅ | — |
| Cross-entity global search | ✅ (`app/library/search.py` + `GET /api/search`) | ✅ `test_global_search` 5 | AUDIT-P8-003 RESOLVED |
| NL edit → EditRequest + impact preview | ✅ (`app/edit/` + `POST /api/library/{id}/edit-plan`) | ✅ `test_nl_to_request` 5 | AUDIT-P8-002 RESOLVED (backend); scene-editor panel UI = LOW |
| Setup Wizard server persistence | ✅ (`finishSetup` → `/api/workspaces` + `/api/brands`) | ✅ `test_setup_wizard_persistence` 2 + `tsc` | AUDIT-P8-004 RESOLVED |
| Cross-channel capacity planner | ✅ (`app/autopilot/capacity.py` + `/api/publishing/calendar/capacity`) | ✅ `test_capacity` 5 | AUDIT-P6-001 RESOLVED |

## Phase 9 — Real-World Validation (2026-09-01)

| Item | Code Ready | Local/Staging Verified | Production Verified | Note |
|---|:-:|:-:|:-:|---|
| Concurrent campaign load (20 in flight) | ✅ | ✅ `test_concurrent_load.py` (0 corruption, pool 11/8 HW) | ❌ real workers | inline runners; a real Celery pool + queue depth under load = NEEDS_PRODUCTION_ENVIRONMENT |
| LEARN_ONLY batch load (100 refs) | ✅ | ✅ `test_learning_load.py` (0 production, cheap-first) | n/a | — |
| Failure/recovery matrix (LLM/search/DB/Redis/worker) | ✅ | ✅ `test_failure_recovery.py` + `test_infra_and_ops.py` (fault injection) | ⚠️ partial | real provider outages / real Redis+DB restarts = NEEDS_PRODUCTION_ENVIRONMENT |
| Publishing duplicate-safety (concurrent + retry + late block) | ✅ | ✅ `test_publishing_safety.py` (1 remote post, idempotent_skip) | ❌ mock platform | real SNS retry semantics = NEEDS_CREDENTIALS |
| Restart-resume, no duplicate provider calls | ✅ | ✅ `test_failure_recovery.py`, `test_checkpoint_resume.py` | ⚠️ | verified with the Postgres checkpointer in-process |
| 12 Phase 1–8 invariants (block re-check) | ✅ | ✅ `test_invariant_recheck.py` (12/12) | ✅ (deterministic) | — |
| Security injection at batch scale (poison / SSRF / redirect-SSRF) | ✅ | ✅ `test_security_load.py` (8/8) | ✅ (deterministic guards) | — |
| Content Library at scale (1000 campaigns) | ✅ | ✅ `test_content_library_scale.py` — **P9-001 fixed** (9.3 s→0.25 s) | ⚠️ | not tested at 100k+; index review deferred |
| Browser E2E (rendered) | ⚠️ HTTP-level only | ✅ `test_e2e_journeys.py` (6/6) + `tsc` + `next build` | ❌ | Playwright = new dev dep (D67); `AVAILABLE_NOT_REQUIRED` |
| QUICK_SOAK | ✅ | ✅ `test_soak.py` — 123 cycles / 180 s, no leak | n/a | FULL_SOAK `AVAILABLE_NOT_REQUIRED` |
| Local backup → verify → restore round-trip | ✅ | ✅ `tests/ops/test_backup_restore.py` (real pg_dump/pg_restore into `acf_restore_test`) | ❌ | off-site / WAL / PITR = NEEDS_PRODUCTION_ENVIRONMENT |
| Off-site backup / WAL / PITR / external monitoring / domain+TLS | — | — | ❌ | **NEEDS_PRODUCTION_ENVIRONMENT** — not faked |
| SNS OAuth / app review / analytics scopes / revenue APIs / paid provider keys | — | — | ❌ | **NEEDS_CREDENTIALS** — not faked |

## Phase 10 — Production V1.0 Release (2026-09-01)

| Item | Code Ready | Local/Staging Verified | Production Verified | Note |
|---|:-:|:-:|:-:|---|
| Version 1.0.0 surfaced (metadata / API / UI / snapshot) | ✅ | ✅ `tests/phase10` | n/a | `config.app_version`, `GET /api/support/version` |
| GLOBAL_PUBLISH_PAUSE → 0 remote publish | ✅ | ✅ `test_kill_switches.py`, `test_release_e2e.py` | ⚠️ mock platform | wired in `run_publish_job` before any remote work |
| GLOBAL_PAID_PROVIDER_PAUSE → 0 cloud calls, local OK | ✅ | ✅ `test_kill_switches.py` | ⚠️ | wired in `ai_router.execute._provider_for` (anthropic) |
| AI Support Snapshot (real data, error taxonomy, trace id) | ✅ | ✅ `test_support_snapshot.py` (13) | n/a | `app/support/` + `/api/support/snapshot` + `/support` |
| Support Snapshot secret redaction | ✅ | ✅ (planted keys/tokens/DSN never leak) | n/a | whole payload via `app/ops/redaction.py` (patterns hardened) |
| Support Snapshot tenant isolation / RBAC | ✅ | ✅ (`ctx.assert_workspace`; admin infra detail; 0 other-tenant) | n/a | — |
| Production config validator | ✅ | ✅ `test_config_check.py` | n/a | `GET /api/ops/config-check`; flags `silent_mock_fallback_in_prod` |
| Responsive dashboard (desktop + mobile shell) | ✅ | ✅ `tsc` + `next build` + HTTP-level journeys | ⚠️ no rendered-browser | `components/AppShell.tsx`; 0 npm deps added |
| Cross-device shared state | ✅ | ✅ `test_release_e2e.py` | n/a | same backend/DB; no client-only critical state |
| GitHub dashboard audit (no template transplant, license/security check) | ✅ | ✅ `DASHBOARD_REFERENCE_AUDIT.md` + `OPEN_SOURCE_COMPONENTS.md` | n/a | 0 files copied, 0 deps |
| Rendered-browser E2E (Playwright) | ⚠️ | HTTP-level only | ❌ | new dev dep (D67); `AVAILABLE_NOT_REQUIRED` |
| Real publish / paid provider probe / analytics / revenue | — | — | ❌ | NEEDS_CREDENTIALS + NEEDS_USER_APPROVAL |
| Domain+TLS / off-site backup / WAL-PITR / external alert delivery / real worker pool | — | — | ❌ | NEEDS_PRODUCTION_ENVIRONMENT |
