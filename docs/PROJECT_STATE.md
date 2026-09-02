# PROJECT STATE

> Read this file + `DECISIONS.md` (+ the `*_CAPABILITIES.md` for Phase 2–4) first
> in every new session. Then read only the files relevant to the current phase.
> **Code is the source of truth** when docs and code disagree.

> Phase-specific capability docs: `PLATFORM_CAPABILITIES.md` (2), `ANALYTICS_CAPABILITIES.md` (3),
> `TREND_CAPABILITIES.md` (4). Phase 5 ops docs: `PRODUCTION_READINESS.md`, `RUNBOOK.md`,
> `DISASTER_RECOVERY.md`, `DEPLOYMENT_CHECKLIST.md`.
> GitHub Best-of-Breed Audit (2026-08-31): `AGENT_SKILL_INVENTORY.md` (every
> component, code-truth), `BEST_SKILL_MATRIX.md` (per-agent OSS comparison +
> decisions). `DECISIONS.md` D59b–D62.
> Advanced Video Studio Upgrade (2026-08-31): `VIDEO_ARCHITECTURE.md` (Director
> team + B1–B109 status), `VIDEO_BEST_SKILL_MATRIX.md` (video OSS + code/model
> licence split). `DECISIONS.md` D63–D66. Code: `backend/app/video/`.
> Content Governance Layer (2026-09-01): `CONTENT_GOVERNANCE.md`, `RIGHTS_LEDGER.md`,
> `ORIGINALITY_ENGINE.md`, `CONTENT_POLICY_CAPABILITIES.md`, `AI_DISCLOSURE.md`,
> `COPYRIGHT_RESPONSE.md`. `DECISIONS.md` D78–D82. Code: `backend/app/governance/`.
> Cross-Phase Intelligence Upgrade (2026-09-01): `URL_LEARNING_ENGINE.md`,
> `LEARNING_STUDIO.md`, `REFERENCE_DATASET.md`, `PROMPT_DISTILLATION.md`,
> `LEARNED_SKILLS.md`, `PLATFORM_SELECTION.md`, `REFERENCE_LIBRARY.md`.
> `DECISIONS.md` D83–D88. Code: `backend/app/intel/`. Migration `0009_intelligence`.
> Phase 8 (2026-09-01): `BEGINNER_GUIDE.md`, `USER_GUIDE.md`, `SETUP_WIZARD.md`,
> `UI_ARCHITECTURE.md`, `CONTENT_LIBRARY.md`, `CONTENT_HISTORY.md`, `LOCAL_AI.md`,
> `MODEL_ROUTER.md`, `MODEL_BENCHMARK.md`, `COST_OPTIMIZATION.md`, `TEST_MODES.md`,
> `LOCAL_START.md`. `DECISIONS.md` D89–D93. Code: `backend/app/ai_router/`,
> `backend/app/library/`, `backend/app/providers/ollama_llm.py`. Migration `0010_phase8`.

## Current Phase
**PHASE 11 — PROVIDER CONNECTIONS: Google AI + ElevenLabs — 2026-09-01.**
Integrated into the existing media provider abstraction — **0 new dependencies**
(stdlib `urllib`, like Ollama), **0 new migrations** (head stays `0011_medium_repair`).
Anthropic stays the primary cloud LLM (not replaced).
- **Google AI**: canonical `GOOGLE_API_KEY`; `IMAGE_PROVIDER=google` →
  `GoogleImageProvider` (Imagen `:predict`); `VIDEO_PROVIDER=google` →
  `GoogleVideoProvider` (Veo `:predictLongRunning` + bounded sync poll → retrieve;
  fits the `VideoProvider` protocol, worker/idempotency model unchanged).
  `get_video_provider()` no longer always None. **Render pipeline still downgrades
  AI_VIDEO to image-motion** (`max_ai_video_ratio` default 0) — adapter connected,
  invocation is an opt-in.
- **ElevenLabs**: canonical `ELEVENLABS_API_KEY` + `TTS_PROVIDER=elevenlabs` +
  `ELEVENLABS_VOICE_ID` (required, no invented default) → `ElevenLabsTTSProvider`
  (`/with-timestamps` + `pcm_24000` in a 24 kHz WAV; accurate duration; no voice
  cloning).
- Model names live only in `config.py`. Keys backend-only, never logged, redacted
  everywhere. `cost=0.0` + `cost_state=UNKNOWN` (media pricing not verified).
- Normalised errors `GOOGLE_* / ELEVENLABS_*` (`app/support/errors.py`) with
  suggested actions; `error_type` stays a standard retry-taxonomy value.
- `GET /api/providers` + AI Support Snapshot `system.cloud_providers.providers`
  report `CONNECTED / NOT_CONFIGURED / DEGRADED / ERROR` for the 5 providers — no
  key value. `/support` page lists each. `GLOBAL_PAID_PROVIDER_PAUSE` falls media
  back to mock. `.env.example` rewritten.
- **Tests** `tests/phase11/` = 32 (all HTTP-mocked, **no paid call**). Affected
  regression 262 passed / 0 failed. `tsc` + `next build` + secret scan clean.
  Invariants held: direct-provider bypass 0, existing Anthropic/Tavily/Ollama
  unchanged, LEARN_ONLY 0 media, paid-provider-pause → mock. `DECISIONS.md` D98.

### Local runtime hardening — 2026-09-02 (no phase, no feature, no migration)
Local Docker stack normalised so `/support` reflects real backend state on a
fresh Windows machine. **0 new deps, 0 migrations** (head `0011_medium_repair`),
`.env` values NOT read out, 0 paid calls, 0 volumes deleted (`pgdata` preserved).
- **Worker registry** (`app/ops/worker_registry.py`): id is now the stable
  `ACF_WORKER_ID` / hostname, not `hostname:pid:uuid`. Celery prefork children no
  longer each register a row that goes stale; `heartbeat()` upserts (no more
  no-op on a missing row); `register_worker` prunes stale same-host rows;
  `_upsert` refreshes `hostname`/`version` so the row tracks the running build.
  Fixes snapshot "Workers/Scheduler DEGRADED".
- **`config.py`**: list envs (`TRUSTED_HOSTS`, `CORS_ALLOW_ORIGINS`,
  `SSRF_ALLOW_HOSTS`, autopilot block-lists) are `Annotated[list[str], NoDecode]`
  + a `mode="before"` validator → accept `*`, comma list, or JSON. pydantic no
  longer crashes on `TRUSTED_HOSTS=*` coming from `.env` via compose.
- **`providers/status.py`**: status vocab `NOT_CONFIGURED / MOCK / CONFIGURED /
  CONNECTED / DEGRADED / AUTH_FAILED / ERROR`. A key present under `MOCK_MODE=true`
  reports **MOCK**, never a false CONNECTED; CONNECTED only after a real free
  read-only probe (Google list-models, ElevenLabs list-voices, Ollama /api/tags).
- **`docker-compose.yml`** (git-untracked): `env_file: .env` + `${VAR:-default}`
  in `environment:` (`.env` is source of truth; `MOCK_MODE` no longer hard-coded);
  `OLLAMA_BASE_URL=http://host.docker.internal:11434` + `extra_hosts: host-gateway`;
  worker healthcheck = `celery inspect ping` (not the image's backend HTTP check);
  frontend `HOSTNAME=0.0.0.0` (Next standalone in-container healthcheck) and **no
  `command:` override** (keeps `node server.js`; `npm run start` → `next: not found`).
- **`backend/Dockerfile`** `ARG APP_VERSION=1.0.0`; `.env` `APP_VERSION=1.0.0` →
  `/api/support/version` and the worker registry now both read `1.0.0`.
- **Scripts**: `scripts/start-local.ps1` (one command: Docker Desktop + Ollama +
  `gemma3:4b` checks → `compose config -q` → build all → up → per-service health
  wait → summary → open dashboard), `stop-local.ps1` (stop / `-Down`; never `-v`),
  `status-local.ps1` (read-only health; providers status only, never a key).
- Verified live: 5/5 containers healthy; `/health/ready` ready; snapshot overall
  OK (backend/db/redis/workers/scheduler/storage/ffmpeg OK, Ollama OK +
  `model_available`); providers anthropic/tavily/google/elevenlabs = MOCK, ollama
  = CONNECTED. Tests `tests/phase11` + `tests/ops` targeted (list below).
  `docs/OPERATIONS_RUNBOOK.md` "Local stack (Windows dev)" + `README` Quick start.

### Prior — PHASE 10 PRODUCTION V1.0 FINAL INTEGRATED RELEASE — 2026-09-01
Version **`1.0.0`** (`config.app_version`; `GET /api/support/version`; OpenAPI; `/support`).
Not a big-feature phase — the Phase 1–9 system finished as a usable product.
**0 new dependencies, 0 new migrations** (head stays `0011_medium_repair`).
- **Production kill switches** (DB-backed, survive restart, real gates):
  `GLOBAL_PUBLISH_PAUSE` → `run_publish_job` short-circuits before any remote work
  (job stays READY); `GLOBAL_PAID_PROVIDER_PAUSE` → `ai_router.execute._provider_for`
  refuses `anthropic`, local Ollama + mock still run; `EMERGENCY_STOP` also pauses
  publish. Toggle `POST /api/ops/flags/<FLAG>`.
- **AI Support Snapshot** — `app/support/snapshot.py` + `GET /api/support/snapshot`
  / `.txt` + `/support` page. One screenshot/copy-friendly diagnostic: version /
  env / health / kill switches / system / current job / pipeline / model routing /
  Ollama / workers+queues / **last error with a normalised code + one-line
  suggested action** (`app/support/errors.py`) / governance+SNS+cost / learning /
  recent events / trace id. Secret-redacted (whole payload through
  `app/ops/redaction.py`, patterns hardened for `sk-ant-` etc.), RBAC-scoped
  (workspace for users, infra detail for admin, 0 other-tenant data). Capture
  mode + "지원 정보 복사".
- **Production config validator** — `app/ops/config_check.py` +
  `GET /api/ops/config-check` (delegates hard prod checks to `app/ops/env.py`);
  per-capability status; flags `silent_mock_fallback_in_prod`.
- **Responsive dashboard** — `components/AppShell.tsx` (desktop grouped nav +
  mobile bottom nav + 더보기 bottom sheet), design tokens (`tailwind.config.ts` +
  `globals.css` `@layer components`). No template transplant, 0 npm deps added
  (`docs/DASHBOARD_REFERENCE_AUDIT.md`, `OPEN_SOURCE_COMPONENTS.md`).
- **Tests**: `tests/phase10/` = 27 (kill switches 5 + support snapshot 13 +
  config check 4 + release E2E 5). Frontend `tsc` + `next build` clean. Secret
  scan clean.
- **Verdict: B — V1.0 RELEASE CANDIDATE READY; REAL CREDENTIAL / INFRA
  VERIFICATION PENDING.** Controlled production pilot (1 content × 1 platform,
  human-approved): YES. Unrestricted full automation: NO. Phase 11 NOT started.
  Docs: `RELEASE_V1.md` + the 18 Phase 10 docs.

### Prior — PHASE 9 REAL-WORLD VALIDATION — 2026-09-01
Not a new product; a validation phase over the locked Phase 1–8 baseline. New
suite `tests/phase9/` = **59 tests, 0 failed**. **Full regression 545 passed / 0
failed / 0 errors** (486 baseline + 59). **1 defect found & fixed (P9-001**,
library pagination O(N) → DB `OFFSET/LIMIT` fast path, 9.3 s → 0.25 s at 1000
campaigns). **0 new deps, 0 new migrations** (head stays `0011_medium_repair`).
- Load: 20 concurrent Phase 1-A pipelines, 0 corruption, DB pool bounded.
  LEARN_ONLY batch 100 → 0 production, cheap-first (deep ≤ top-20, 0 premium LLM).
- Failure/recovery: LLM retry taxonomy, search honest-fail, DB reconnect,
  rollback no-orphan, Redis-down graceful, **restart-resume 0 dup AgentRuns**,
  cancel 0 new work.
- Publishing: concurrent double-fire → 1 remote post; retry → idempotent_skip;
  rights-expiry after queue → 0 remote.
- Security at batch scale: poisoned ref → 0 execution; SSRF + redirect-SSRF
  blocked end-to-end; internal Ollama path unaffected.
- All 12 Phase 1–8 invariants re-verified as a block.
- QUICK_SOAK 180 s / 123 cycles: heap flat, pool flat, 0 failed, no leak.
- Browser E2E: HTTP-level journeys (6, all pass) + `tsc` + `next build` clean;
  rendered-browser Playwright = AVAILABLE_NOT_REQUIRED (new dev dep needs D67).
- **Verdict: B — PHASE 9 LOCAL/STAGING VALIDATION COMPLETE, PRODUCTION
  VERIFICATION PENDING.** Can proceed to Phase 10: YES (do NOT start unprompted).
  See `docs/PHASE9_REAL_WORLD_VALIDATION.md` + the tier docs; `DECISIONS.md` D96.

### Prior — MASTER MEDIUM GAP REPAIR (Phase 1–8 baseline hardening) — 2026-09-01.
Not a new phase. All **7 MEDIUM implementation gaps RESOLVED** (each with targeted
tests); **`PHASE_1_8_FUNCTIONAL_BASELINE_LOCKED`**. 0 CRITICAL, 0 HIGH, **0 MEDIUM**
implementation gaps, 5 LOW (unchanged). Production verification (credentials /
environment) stays PENDING — not an implementation gap.
- **AUDIT-P8-006** — PromptComposer now on the real agent path:
  `model_gateway._compose_system()` merges Base + Brand + Channel + Memory +
  agent/platform/brand-filtered Learned Skills + Prompt Blueprints under the token
  budget BEFORE routing; honours the user disable switch; lineage persisted to
  `ModelRoutingEvent.prompt_lineage` (migration `0011_medium_repair`). Retrieval is
  deterministic (no extra LLM). AUDIT-P8-001 bypass guard still 0.
- **AUDIT-P8-005** — `ModelRouter.select(db=…)` reorders candidates by learned
  `ModelPerformance` strength (STRONG↑ / WEAK↓), guarded by the min-sample floor.
- **AUDIT-P8-003** — `GET /api/search` + `app/library/search.py` across
  campaign/platform-content/channel/brand/reference/publication.
- **AUDIT-P8-002** — `app/edit/nl_to_request.py` deterministic NL→EditRequest +
  `impact_of()` (Smart-Rerender preview) + `POST /api/library/{id}/edit-plan`.
- **AUDIT-P8-004** — Setup Wizard "설정 완료" POSTs `/api/workspaces` + `/api/brands`
  (`finishSetup`); `create_workspace`/`create_brand` now commit.
- **AUDIT-P6-001** — `app/autopilot/capacity.py` per-channel daily slots + budget
  headroom; Autopilot caps its run by it; `GET /api/publishing/calendar/capacity`.
- **AUDIT-P7-001** — `app/governance/policy_verify.py` human-in-the-loop policy
  review queue + attested `record_verification`; `GET/POST /api/policy/verif*`.

### Prior — MASTER IMPLEMENTATION AUDIT (Phase 1–8) + AUDIT-P8-001 REPAIR
The audit's one HIGH blocking gap is **RESOLVED**: every
production agent LLM call now routes through `app/agents/model_gateway.py` →
`ai_router.run_routed` (ModelRouter + per-agent policy + escalation + LOCAL_ONLY +
telemetry). Evidence: a light agent task provably runs on `gemma3:4b`
(provider=ollama, real local call); a full Research→Fact→Strategy→Hook→Script run
emits ≥4 `ModelRoutingEvent` rows across `standard` + `premium` tiers; a static
guard forbids re-introducing a direct provider call. No schema change, no new
dependency. `tests/agents/test_model_gateway.py` = 15.
**Audit verdict: B — Phase 1–8 functionally complete, production verification
pending** (credentials / environment only). 0 CRITICAL, 0 HIGH, 7 MEDIUM, 5 LOW.
**Can proceed to Phase 9: YES** (do NOT start unprompted). See
`docs/MASTER_IMPLEMENTATION_AUDIT.md`, `FEATURE_COVERAGE_MATRIX.md`,
`PRODUCTION_VERIFICATION_MATRIX.md`, `TECH_DEBT_AND_GAPS.md`,
`artifacts/master_audit.json`.

**Full regression after the repair (2026-09-01): 449 tests, 0 failed, 0 errors,
0 skipped** — run in 7 sub-batches (env kills >13-min jobs), totals from per-batch
JUnit XML: agents 15 · ai_router+autopilot 61 · 10 root test files 46 ·
phase8_e2e+intel 75 · governance+mb 88 · library+media+analytics 49 ·
ops+publishing+video 115. Baseline was 434; +15 = the new
`tests/agents/test_model_gateway.py`.

### Prior — PHASE 8 delivered
**PHASE 8 — Beginner UX + Content Library + Local AI + Model Router + Cost
Optimization.** Implemented + tested (434 baseline; +15 gateway tests in the repair).

- **Local AI**: `providers/ollama_llm.OllamaLLMProvider` (stdlib HTTP, no `ollama`
  pkg) — same `.complete` contract as cloud; `health()`/`list_models()`/`ping`.
  **LOCAL_VERIFIED**: Ollama 0.33.2 + `gemma3:4b` reachable, JSON inference OK.
  App never crashes when Ollama is down; `ALLOW_CLOUD_FALLBACK=false` = LOCAL_ONLY.
- **Model Router** (`ai_router/`): tiers deterministic (Python, no model) /
  local_light (Ollama first) / standard / premium. Weighs task fit + quality +
  cost + latency + reliability + privacy — never price alone. `run_routed`
  escalates on schema-invalid / low-confidence, bounded fallback chain, honours
  LOCAL_ONLY. `hash`/`classification` never reach premium even at `max`.
  `ModelRegistry` (health-probed), routing telemetry + `ModelPerformance` memory
  (UNKNOWN until `MODEL_ROUTING_MIN_SAMPLE`=8). Benchmark service on our task set.
- **Cost Estimator** (`ai_router/cost.py`): per-category KNOWN/ESTIMATED/UNKNOWN;
  media = UNKNOWN (MOCK), never fabricated; local = "LOCAL PROCESSING · API ₩0";
  shared assets counted once; recomputes on SNS change.
- **Content Library** (`library/`): read model over Campaign/PlatformContent/
  Asset/Script/Publication/Analytics/Revenue/Cost — **discovers ALL existing
  content incl. pre-governance legacy** (LEGACY badge, no crash). Card + table,
  search, filter, server pagination; 12-tab detail; real MP4 streamed via
  `/api/library/{id}/media/video`; demo renders flagged `is_demo`; add-platform-
  later generates only the new platform.
- Migration `0010_phase8` (2 tables, additive). `.env.example` + `scripts/
  start-local.ps1`/`stop-local.ps1` added (never reset DB).
- Frontend: `/create`, `/library`, `/library/[id]`, `/setup` (8-step resumable),
  `/settings/local-ai`, `/calendar`, `/system` — Korean-first, beginner-default,
  status-by-text; `tsc` + `next build` clean (~24 routes).
- `tests/ai_router/` = 35, `tests/library/` = 13, `tests/test_phase8_e2e.py` = 3.
  0 new runtime dependencies. pytest markers added (fast/media/integration/…).
- **STOP — do not start Phase 9.**

### Prior — CROSS-PHASE INTELLIGENCE UPGRADE complete
**URL Learning / Reference Dataset / Prompt Distillation / Agent Skill Learning /
SNS Platform Selection.** `backend/app/intel/` reuses Research / Fact Check /
Memory / Learning / Video Studio / Governance / Publisher / Analytics.

- **URL Learning Engine** (`intel/engine.py`): validate (SSRF, per-redirect) →
  fetch (http; browser adapter opt-in) → clean/extract (stdlib `html.parser`,
  strips chrome) → **prompt-injection scan + sanitize** (external content is
  UNTRUSTED, never executed) → cheap quality + dedup → semantic chunks → deep
  analysis on the top-K → dataset → distillation → skill notes → memory. Hard
  guards on item count / daily count / bytes / cost.
- **Execution modes**: `CREATE_ONLY` / `CREATE_AND_LEARN` (default) / `LEARN_ONLY`
  / `REFERENCE_ONLY`. `assert_no_production_side_effects` + gates in
  `create_jobs_for_campaign` and `run_publish_job` guarantee LEARN_ONLY makes no
  Campaign / media / render / PublishJob / SNS call.
- **Reference Dataset Engine** (`intel/dataset.py`, `intel/quality.py`):
  `DataQualityScore` + `learning_weight`; dedup (canonical URL / content hash /
  simhash / semantic / `text_similarity`); `DataCurator` down-weights + deactivates
  duplicate/spam/rights-problem records. One `reference_analysis` table (keyed by
  `analysis_kind`) replaces a dozen profile tables.
- **Video deep analysis** (`intel/analyzers.py`): `VideoObservation` + 10 sub-
  profiles from a **caller-supplied structured profile only** — every unmeasurable
  field is `UNKNOWN`, no fabricated numbers. Real frame CV is an OPTIONAL adapter.
- **Prompt Distillation** (`intel/distillation.py`): `PromptBlueprint` =
  reverse-inferred production guidance (never the creator's original prompt, never
  verbatim source text). Single-source guard (1 ref ≤ EXPERIMENTAL);
  multi-reference confidence; state machine OBSERVED→EXPERIMENTAL→CANDIDATE→
  VALIDATED→PROMOTED + rollback; `AUTO_PROMOTE_LEARNED_PROMPTS=false` (human or a
  VALIDATED experiment promotes); traceable `PromptBlueprintEvidence`.
- **Agent Skill Learning** (`intel/skills.py`): `LearnedSkillNote` (testable rule +
  evidence + confidence + sample size) per agent; `CreativeRecipe` (best sub-
  profile from several references). `intel/gap.py` recommends what to learn next
  from weak Analytics dimensions.
- **PromptComposer** (`intel/composer.py`): BASE + BRAND + CHANNEL + MEMORY +
  LEARNED_GUIDANCE under a token budget; agent- and platform-specific retrieval;
  production default injects only PROMOTED blueprints.
- **SNS Platform Selection** (`intel/platform_selection.py`): 3-state per
  platform/content-type (`DISABLED` / `GENERATE_ONLY` / `GENERATE_AND_PUBLISH`).
  Check-off skips **generation**, not just publishing (`Campaign.platforms` = the
  non-DISABLED set). Publisher re-checks the selection right before the API call
  (queued-job race). User-explicit selection locks the campaign; Autopilot cannot
  re-enable. Cost preview = `PRICING_UNKNOWN` while media is MOCK.
- **Governance integration** (`intel/reference_guard.py`): generated Hook / Title /
  Script similarity-checked vs the campaign's learned references → governance
  `FIX_REQUIRED`; no-op when there are no references.
- Migration `0009_intelligence` (13 tables + 3 NULLABLE columns, additive,
  ORM-mapped). `tests/intel/` = 66 + 1 integration E2E. Frontend: `/compose`,
  `/learn-studio`, `/references`, `/prompt-lab` (17 routes, tsc + build clean).
- **STOP — do not start Phase 8 (Beginner UX / Setup Wizard / One-click Operation).**

### Prior — PHASE 7 complete
**PHASE 7 — Copyright / Rights / Policy / Originality / AI Disclosure / Content
Governance.** COMPLETE + tested. A deterministic pre-publish gate
(`app/governance/`, no LLM verdict) that tracks source / licence / commercial-use /
AI-generation / edit-transform / person-brand risk / originality / duplicate /
platform policy / ad-affiliate disclosure / fact provenance across the whole
pipeline and returns ALLOW / ALLOW_WITH_DISCLOSURE / ALLOW_WITH_ATTRIBUTION /
FIX_REQUIRED / HUMAN_REVIEW / BLOCK. Wired into the **Publisher**
(`run_publish_job` → `govern_pre_publish`, before the platform call) and
**Autopilot** (`bridge.produce_from_context` → `govern_campaign(stage=post_render)`,
no jobs on hold); both fail safe. Unclear rights ⇒ `UNKNOWN_RIGHTS` ⇒ hard block
from FULL_AUTO/AUTOPILOT/SEMI_AUTO. Hard blocks are AI/UI-unclearable
(`_HARD_BLOCK_CODES`). `RightsManifest` built from the assets actually in the
render + render file hash. Migration `0008_governance` (14 tables + 4 NULLABLE
columns, additive). `tests/governance/` = 46 (28 units + 13 gate + 5 e2e). Docs:
`DECISIONS.md` D78–D82 + the 6 governance docs above. Legacy campaigns
(`workspace_id IS NULL`, no ledger) short-circuit to
`GOVERNANCE.NOT_APPLICABLE_LEGACY`. **STOP — do not start Phase 8 (Beginner UX /
Setup Wizard / One-click Operation).**

### Prior — PHASE 6 complete
**PHASE 6 — Multi-Brand / Multi-Channel / Portfolio / Monetization.** Core loop
COMPLETE + tested: auth + RBAC (`app/auth/`), tenant + credential isolation
(`app/mb/scope.py`, `token_manager.assert_credential_scope`), hierarchical hard
budget with transactional reservation (`app/mb/budget.py`), deterministic Channel
& Portfolio managers, content routing + cannibalization guard, Monetization
agent + sponsor/commercial/affiliate guards, `/portfolio` dashboard,
multi-channel mock e2e, brand/channel/workspace pause. Migration `0007_multibrand`
(20 tables, additive). `tests/mb/` = 42. Docs: `MULTI_BRAND_ARCHITECTURE.md`,
`CHANNEL_MANAGER.md`, `PORTFOLIO_MANAGER.md`, `MONETIZATION.md`, `SECURITY_MODEL.md`;
`DECISIONS.md` D71–D77. Long tail (scheduler/capacity, autopilot beat wiring,
reposition LLM, wizards, report generators, full audit coverage, load fixtures) is
DESIGN_ONLY.

### Prior — PHASE 5 complete + special upgrade passes:
(a) GitHub Best-of-Breed Agent Audit — `AGENT_SKILL_INVENTORY.md` / `BEST_SKILL_MATRIX.md`, 3 safe fixes (D60).
(b) Advanced Video Studio Upgrade — `app/video/` deterministic Director team, additive to the media pipeline (D63–D66).
(c) Continuation pass (D67–D70): **agent-core A-tier implemented** — Research query decomposition + rank + contradictions (`app/agents/research.py`), Fact Checker atomic claims + agreement + confidence blend (`app/agents/factcheck.py`), Hook diversity + exaggeration guard (`app/agents/hooks.py`), Memory keyword-fusion; **video engines** Cut Engine V2, Caption Collision, Creative QA V2, Smart Rerender, Technical QA V2, pause classification, cognitive-load actions, quality 0–100 + repair plan; **Video Studio dashboard** (`/campaigns/[id]/studio`). 0 new dependencies. Install policy D67: no global tools / user plugins.
Phase 6 (Multi Brand / Channel / Monetization) NOT started.

### Phase 5 baseline
**PHASE 5 — Production / Security / Backup / Monitoring / Recovery.** Code +
offline/local-staging tests COMPLETE. Real backup→verify→restore round-trip
verified via `docker exec` pg_dump/pg_restore into `acf_restore_test`. Items that
need real infrastructure (prod server / domain / TLS / cloud bucket / SNS creds —
none supplied) are **CODE READY / LOCAL-STAGING VERIFIED /
NEEDS_PRODUCTION_ENVIRONMENT**, see `docs/PRODUCTION_READINESS.md`. Phases 1-A,
1-B, 2, 3, 4 remain COMPLETE and un-regressed. **Do not start Phase 6.**

## Completed — Phases 1-A / 1-B / 2 / 3 (unchanged)
- **1-A** Topic → Research → Fact Check → Strategy → Hook → Master Script (+ Natural Writing). LangGraph + Postgres checkpointer. Alembic `0001`.
- **1-B** Knowledge Pack → platform-native content → scenes → cost-aware Visual Director → media → FFmpeg render → thumbnail + platform images → QA → scene regen. Alembic `0002`. Media MOCK.
- **2** Publishing engine: 10 publishers, OAuth + Fernet crypto + TokenManager, DB scheduler, idempotency + crash reconciliation, preflight + normalizer, retry/DLQ, polling, remote verification, HMAC webhooks, `DRY_RUN` default. Alembic `0003`. Publishers MOCK.
- **3** Analytics + Learning + Memory + Revenue: capability-gated analytics providers (unsupported metric → null + status, never 0), time-series snapshots, feature store, baselines/scores, evidence-based Learning Engine + false-learning guard, 16 memory types + bounded retrieval + strategy injection, content recipes, sequential experiments, reports, opportunity inputs. Alembic `0004`. Analytics MOCK.
- **4** Trend Intelligence + Opportunity Engine + AUTOPILOT: 10 capability-gated trend providers (mock), two-stage opportunity scorer (17 dims, explainable), portfolio with diversity/budget guards, AutopilotContext bridge reusing the 1-A→1-B→2 pipeline, pre-publish recheck (sunk cost ignored), watchdog + emergency stop, HARD RULES AI-immutable. Alembic `0005`. Trends MOCK, `DRY_RUN`.

## Completed — Phase 4
- **Trend Capability Registry** (`app/trends/capabilities.json` + loader): 10 sources, `auth_status` from official docs 2026-08-31 (`docs/TREND_CAPABILITIES.md`). `APPROVAL_REQUIRED`/`LIMITED`/`UNAVAILABLE` never faked as `AVAILABLE`; platforms without a public API are not scraped.
- **TrendProvider interface** (`base.py`): `get_capabilities / fetch_trending / search_topic / get_topic_history / get_velocity_data / get_source_metadata`. 10 named providers (`YouTube/GoogleTrend/WebSearch/News/Naver/Reddit/OwnAnalytics/TikTok/X/Threads`) over a client abstraction. `OwnAnalyticsTrendProvider` mines Phase 3 features for evergreen candidates (always available). Mock client = deterministic 60-topic catalogue with breakout/rising/stable/declining/evergreen shapes, risk/competition hints, near-duplicates. Real `HttpTrendClient` raises `PERMISSION_MISSING`.
- **Schema** (`db.models` + Alembic `0005`): `trend_sources`, `raw_trend_events` (24h dedup key), `topic_candidates` (17 sub-scores + risk + platform_scores + opportunity + portfolio + explanation), `autopilot_runs`, `autopilot_decisions` (append-only log), `autopilot_config_versions`, `topic_rejections` (ONCE vs PERMANENT).
- **Ingest** (`trends/ingest.py`): scans `active_source_ids()` (OWN_ANALYTICS + AUTH_REQUIRED); writes `RawTrendEvent` with `sha256(source|normalized_topic)` dedup (skip if seen in 24h); per-source health/isolation (one source's failure never blocks another); reports `skipped` sources.
- **Autopilot config + HARD RULES** (`autopilot/config.py`): `enforce_hard_rules` — a non-`user` actor (the AI/LLM) **cannot** change `daily_hard_budget / monthly_hard_budget / daily_post_limit / blocked_topics / blocked_keywords / min_compliance_score / emergency_stop`. `apply_config(actor=...)` versions every change into `autopilot_config_versions`. `topic_blocked()` matches blocked topic/keyword substrings.
- **Signal sub-scores** (`autopilot/signals.py`, pure): velocity, acceleration, `trend_status` (BREAKOUT/ACCELERATING/RISING/STABLE/DECLINING/SATURATED/UNKNOWN), `trend_type` + per-type TTL, freshness, competition, saturation (≠ competition), risk level + categories (MEDICAL/FINANCIAL/LEGAL/POLITICAL/ELECTION/… — ELECTION & MEDICAL escalate; TRAGEDY/MINORS → CRITICAL), difficulty (LOW→VERY_HIGH), **NaturalContentOpportunityScore** (does the topic afford concrete examples / data / a human angle, or is it slop-bait?), fact-availability precheck, production-cost estimate.
- **Dedup + clustering** (`autopilot/dedup.py`): cluster assignment via the (improved, particle-aware) cheap embedding; duplicate guard vs published topics over 7/30/90-day windows → `NEW / SIMILAR / DUPLICATE / NEW_ANGLE` with a score penalty; the candidate's own just-created campaign is excluded from its recheck.
- **Historical** (`autopilot/historical.py`): reuses Phase 3 — historical / audience-fit / revenue sub-scores from topically-similar `PerformanceScore` rows with **outliers & anomalies excluded** (one viral clip can't inflate the historical score); `fatigue_score` reads Phase 3 TOPIC-fatigue memories.
- **Opportunity Scorer** (`autopilot/scoring.py`): 17 dimensions → 0–100. Bad dimensions (competition/saturation/fatigue/risk/difficulty/cost) enter inverted. Objective weight tables for VIEWS/FOLLOWERS/REVENUE/PROFIT/BRAND/BALANCED, renormalized over present dimensions, `opportunity_formula_v1` stamped. Output is **explainable** — component scores + human reasons. Per-platform scores via platform-specific dimension tilts.
- **Candidate pipeline** (`autopilot/pipeline.py`): RawTrendEvent → LLM topic-extract (2 angles) → cluster + dedup + block check → **Stage-1 cheap pre-score** (trend/freshness/dedup/basic competition) → keep top `STAGE1_KEEP` → **research/fact precheck** → **Stage-2 full score** → keep top `STAGE2_KEEP`. Two-stage keeps expensive work off weak candidates.
- **Portfolio** (`autopilot/portfolio.py`): not top-N — CORE/TREND/EVERGREEN/REVENUE/EXPERIMENT mix, **diversity guard** (one cluster can't dominate), **dynamic count** (min/max bounded by strong-opportunity availability), **non-uniform budget allocation** (higher opportunity → more budget; experiment → less), **trend reserve** held back for breakouts, production profile FAST/STANDARD/PREMIUM with a **premium guard** (budget allocator must approve).
- **Platform selection** (`autopilot/platform_select.py`): per-topic platform score threshold (or all if `PUBLISH_ALL_PLATFORMS`), Phase 2 capability + account-health awareness (won't plan public auto-posting where it isn't possible), content-type per platform.
- **AutopilotContext** (`autopilot/context.py`): full hand-off object (topic, angle, scores, platform recs, content types, production profile, hook direction, estimated cost, risk, deadline, source ids, decision reasons) — the campaign pipeline gets context, not just a topic string.
- **Bridge** (`autopilot/bridge.py`): **reuses** `run_pipeline` (1-A) → `run_media_pipeline` (1-B) → `create_jobs_for_campaign` (2). Idempotent by `candidate_id` (crash-safe). **Risk matrix overrides run mode**: CRITICAL → jobs MANUAL (never auto), HIGH → SEMI_AUTO, else per mode. Publish time from Phase 3 TIMING memory or a staggered default.
- **Pre-publish recheck** (`autopilot/recheck.py`): before publishing a produced campaign — trend still alive? opportunity dropped? duplicate appeared? risk up? → `CONTINUE / UPDATE_RESEARCH / HOLD / CANCEL`. **Sunk cost is not a reason to publish a dead trend** — cancellation reason stored.
- **Watchdog** (`autopilot/watchdog.py`): runaway cost (vs HARD budget), too many posts/24h, duplicate campaigns, high QA-failure rate, repeated auth failure → triggers → run `PAUSED`.
- **Emergency stop / pause** (`autopilot/emergency.py`): STOP sets a hard flag (new runs refused), stops runs, cancels SELECTED candidates + holds READY/SCHEDULED/QUEUED publish jobs — **never touches a job already UPLOADING/PROCESSING on a remote platform** (Phase 2 rule). PAUSE lets in-flight work finish, starts nothing new.
- **Health gate** (`autopilot/health.py`): checks LLM/search/DB/redis/storage + optional image/video/tts/publishers before a run; required-provider DOWN → run `HOLD`.
- **Calibration** (`autopilot/calibration.py`): predicted Opportunity vs actual relative performance per produced candidate → over/under-prediction → a `SCORE_CALIBRATION` learning memory + nudges each `TrendSource.value_score`.
- **Backtest** (`autopilot/backtest.py`): replays the current formula over past Phase 3 data to show which topics it would pick — labelled a scorer diagnostic, **not a performance guarantee**.
- **Reports** (`autopilot/reports.py`): daily report (sources checked, candidates found/rejected, selected, produced, scheduled, cost, warnings, full decision log) + weekly autopilot report (selection accuracy, opportunity-prediction calibration, best/worst trend source, cancelled trends, source value scores).
- **Controller** (`autopilot/controller.py` / `run_autopilot`): OFF → nothing; emergency-stop flag → refuse. Creates `AutopilotRun`, health gate, scan → candidate pipeline → portfolio → contexts. **SHADOW & SUGGEST_ONLY stop here with ZERO production/publish.** SEMI_AUTO / FULL_AUTO call the bridge, then the watchdog (triggers → `PAUSED`). Resumable via `resume_run_id` (portfolio returns the run's existing selections; bridge idempotent → no duplicate campaigns). **The AI never edits source code** — only tunable weights/preferences.
- **Tasks + beat**: Celery `autopilot` queue + `autopilot_run` / `autopilot_breakout_watch` (SHADOW-level) / `autopilot_calibration`; beat daily.
- **API** (`routes_autopilot.py`): config get/set (hard-rule 403), status, scan, pause/resume, emergency-stop/resume-stop, runs list + detail, candidates + `why-this-topic`, reject (ONCE|PERMANENT), trend-sources, daily/weekly report, backtest, health.
- **Dashboard**: `/autopilot` — mode, today budget + trend reserve, candidate/strong/selected/producing/scheduled counts, Scan (per mode), **AUTOPILOT 긴급 중지**, opportunity candidate list with all sub-scores + platform scores + `왜 추천?` + Reject / Block.

## Completed — Phase 5  (`backend/app/ops/`, Alembic `0006_production`)
- **Structured logging + correlation id** (`ops/logging_config.py`): JSON in prod/staging, plain in dev, `SecretRedactionFilter` on root, per-request id contextvar (honours `x-correlation-id`), silences `uvicorn.access`.
- **Secret redaction** (`ops/redaction.py`): key regex (pass/secret/token/api_key/authorization/cookie/…) + value patterns (Bearer, `ghp_`, `sk-`, `ya29.`, `AKIA`, `xox[baprs]-`, JWT, Fernet `gAAAAA…`, DSN-with-password). `redact()` recurses nested JSON; the global exception handler scrubs the 500 body (prod hides it entirely).
- **Env validation** (`ops/env.py`): `validate_environment()` at `main.py` import — **raises** in production on missing `SECRET_KEY`/`ACF_MASTER_KEY`, `CORS`/`TRUSTED_HOSTS` = `*`, localhost OAuth callback, bad numeric config; warns in dev. Fail-closed.
- **Secrets** (`ops/secrets.py`): `EnvSecretManager` / `DockerSecretManager` (`/run/secrets/<key>` → env fallback).
- **SSRF filter** (`ops/ssrf.py`): `is_safe_url` / `require_safe_url` — blocks non-http(s), localhost, `.internal`, metadata hosts; resolves DNS and rejects private/loopback/link-local/reserved IPs; `SSRF_ALLOW_HOSTS` escape hatch.
- **Upload security** (`ops/upload_security.py`): magic-byte `sniff_mime`, `validate_upload` (sniff vs declared vs size), `safe_filename` (uuid4 + sanitized ext), `has_path_traversal`.
- **Runtime flags** (`ops/runtime_flags.py`): `EMERGENCY_STOP` / `SAFE_MODE` / `MAINTENANCE_MODE` in `runtime_settings` (3 s cache) + `AuditEntry` per change; **persist across restart**. Mirrored from `autopilot/emergency.py`.
- **Metrics** (`ops/metrics.py`): thread-safe counter/gauge/histogram, `render_prometheus()` (0.0.4 text, live DB-pool + Redis-queue gauges). No external dep — a real Prometheus scrapes `/metrics` directly.
- **Health** (`ops/health.py`): `check_database/redis/storage/queue`; `/health/live` (always 200 if process up), `/health/ready` (503 if DB/Redis/storage down or maintenance), `/health/dependencies`, `deep_health(force)` (60 s cache, probes providers). Storage check = disk % vs `DISK_WARN_PCT`/`DISK_CRITICAL_PCT`.
- **Circuit breaker** (`ops/circuit_breaker.py`): CLOSED/OPEN/HALF_OPEN per provider; opens after `PROVIDER_BREAKER_THRESHOLD`, fast-fails `CircuitOpen` for `PROVIDER_BREAKER_COOLDOWN_S`, single half-open probe.
- **Alerts** (`ops/alerts.py`): `raise_alert()` dedup by fingerprint + per-severity cooldown; `count`/`last_seen` bump; `notified` only on first fire / after cooldown. `NotificationProvider` interface, `DashboardNotifier` default, `register_notifier()` for real channels (none supplied).
- **Worker registry + leases** (`ops/worker_registry.py`): `workers` table heartbeat (STALE/DEAD by age), `job_leases` unique `(job_kind, job_id, released)` → duplicate-execution guard; `acquire_lease` reclaims only **expired** leases; `scan_stuck_jobs()` releases expired + HIGH alert. Celery signals `worker_ready`/`task_prerun`/`task_postrun`/`worker_shutdown` wired.
- **DLQ** (`ops/dlq.py`): `dead_letters` table; `_NON_RETRYABLE = {AUTH_ERROR, AUTH_REVOKED, PERMISSION_MISSING, POLICY_REJECTION, BUDGET_EXCEEDED, DUPLICATE}` never auto-retry; `retry_from_dlq` re-enqueues via the original path.
- **Queue backpressure** (`ops/queue_backpressure.py`): Redis LLEN per queue → NORMAL/SLOW/HOLD (`QUEUE_BACKPRESSURE_WARN`/`_HOLD`); `production_allowed()` wired into `controller.run_autopilot` → HOLD `stage="backpressure"`.
- **Cost anomaly** (`ops/cost_anomaly.py`): rolling median × `COST_ANOMALY_FACTOR` per campaign / provider-daily / LLM-token-surge → HIGH/WARNING alert.
- **Backup / restore** (`ops/backup.py`): `run_backup("full"|"storage")` — `pg_dump -Fc --no-owner --no-privileges` + sha256 + optional Fernet + `BackupManifest` + retention; tool resolved **setting → PATH → `docker exec <postgres_container>`**. `verify_backup` = checksum + `pg_restore --list` → VERIFIED/FAILED. `restore_to(id, target_db)` **refuses the source DB**, DROP/CREATE target, `pg_restore --clean --if-exists`, re-verifies `alembic_version` + table counts via a fresh engine → RESTORE_TESTED. `_run_storage_backup` tars CRITICAL+REGENERATABLE assets.
- **Storage integrity** (`ops/storage_integrity.py`): `classify()` CRITICAL/REGENERATABLE/CACHE/TEMP; `scan_assets()` flags MISSING_ASSET/CORRUPTED, restores SUCCESS when fixed, HIGH alert on findings.
- **Rate limit** (`ops/rate_limit.py`): token bucket per (route class, client), `_LIMITS` per class (auth/campaign_create/media/publish/analytics/autopilot/webhook/metrics/default), `classify_path`; `RateLimited` → 429 + Retry-After in `OpsMiddleware`.
- **Middleware** (`app/main.py` `OpsMiddleware`): 413 on oversized `content-length`; 503 in maintenance mode; rate limit → 429; correlation id; per-request metrics (`acf_http_requests_total`, `acf_http_request_seconds`, `acf_http_5xx_total`); security headers (nosniff, DENY, no-referrer, HSTS in prod). CORS + `TrustedHostMiddleware` env-aware. `docs_url=None` in prod. Global exception handler → scrubbed 500.
- **DB** (`app/db/base.py`): prod/staging pool (`pool_size=10`, `max_overflow=10`, `pool_recycle=1800`, `statement_timeout=60000`, `idle_in_transaction_session_timeout=120000`). Alembic `0006` adds `runtime_settings`, `config_change_log`, `workers`, `job_leases`, `backup_manifests`, `ops_alerts`, `audit_log`, `dead_letters` + partial-unique indexes on `publish_jobs.idempotency_key`, `analytics_snapshots (publication_id, window_label)`, `publications.publish_job_id` + perf indexes.
- **API** (`api/routes_ops.py`): `/health/live|ready|dependencies|`, `/health`, `/metrics`; `/api/ops/` `status`, `deep-health`, `workers`(+`/scan-stuck`), `queues`, `alerts`(+`/{id}/resolve`), `dlq`(+`/{id}/retry|resolve`), `flags/{flag}` (SAFE/MAINTENANCE only, `confirm=true`), `backups`(+`/run`,`/{id}/verify`), `cost-anomaly/check`, `storage/integrity`, `_debug/boom` (non-prod).
- **Docker** (`backend/Dockerfile`): multi-stage, adds `postgresql-client` + `ffmpeg`, `ARG APP_VERSION`, non-root `appuser` (uid 10001) + chowned writable dirs, `HEALTHCHECK` → `/health/live`. **`docker-compose.prod.yml`**: `APP_ENV=production`, no bind mounts, `restart: unless-stopped`, resource limits, `${VAR:?}` secret guards, PG/Redis ports unpublished, queue-split workers (`worker`/`worker-media`/`worker-analytics`/`worker-autopilot`), optional Caddy `proxy` profile (`deploy/Caddyfile`). `docker compose config` validates.
- **Security scanner** (`scripts/security/scan_secrets.py`): 10 secret rules + tight allowlist; runs clean on the repo; CI test plants a `ghp_` PAT and it is caught.
- **Frontend** (`frontend/app/admin/page.tsx` + `lib/api.ts`): Ops page — system health, runtime flags (with confirm), workers + scan-stuck, queues, open alerts (resolve), DLQ (retry/resolve), backups (run/verify with confirm), cost-anomaly + storage-integrity checks. Nav link added. `tsc` + `next build` clean (10 routes).
- **Optional observability**: `OTEL_ENABLED` / `SENTRY_DSN` are interface-reserved no-ops (no endpoint/DSN supplied). No new runtime dependency in Phase 5 — see `docs/OPEN_SOURCE_COMPONENTS.md`.
- New docs: `PRODUCTION_READINESS.md`, `RUNBOOK.md`, `DISASTER_RECOVERY.md`, `DEPLOYMENT_CHECKLIST.md`.

## Verified (this session)
- **PHASE 10 — Production V1.0**: `tests/phase10/` = **27 passed** (kill switches 5,
  AI Support Snapshot 13, config validator 4, release E2E 5). **Full regression
  572 passed / 0 failed / 0 errors** (Phase 9 baseline 545 + 27; run in 6 batches
  — pr1 phase10+ai_router+agents 91, pr2 ops+publishing 75, prA
  intel+library+edit+governance 147, prB mb+autopilot+analytics+root 140, prC
  media+video 60, prD phase9 58 + soak 1). Frontend `tsc --noEmit` + `next build`
  clean (`/support` 3.68 kB, shared JS 103 kB — no bloat). Secret scan clean.
  Migration head `0011_medium_repair` (single). Kill switches wired to real gates
  (publish pause → `run_publish_job` short-circuit; paid provider pause →
  `_provider_for` refuses anthropic, local OK). AI Support Snapshot: real data,
  secret-redacted (planted keys/tokens/DSN never leak), workspace-scoped +
  admin-only infra detail (0 other-tenant), per-failure error code + suggested
  action, capture mode + copy text.
- **AUDIT-P8-001 repair (MASTER GAP REPAIR)**: `tests/agents/test_model_gateway.py`
  = **15 passed** — static bypass guard (no `get_llm_provider()` in `agents/nodes.py`,
  `agents/media_nodes.py`, `autopilot/pipeline.py`); agent policy sets tier
  (research/fact/platform_adapt/scene_plan → standard, strategy/hook/script →
  premium); a gateway call writes a `ModelRoutingEvent` with campaign+workspace id;
  **a light agent task (`scene_plan`) provably runs on `gemma3:4b`, provider=ollama**
  (real local call); schema-invalid local output escalates (`escalated` +
  `fallback_used`, no loop); **LOCAL_ONLY + local down → 0 cloud calls**; cloud
  fallback only when `allow_cloud_fallback`; a full `run_pipeline` emits ≥4
  `ModelRoutingEvent` rows across `standard`+`premium`. **Full regression: 449
  passed / 0 failed / 0 errors** (7 sub-batches, per-batch JUnit XML).
- **Phase 8**: `tests/ai_router/` (**35**) + `tests/library/` (**13**) +
  `tests/test_phase8_e2e.py` (**3**) all pass. Coverage of the completion gate:
  Ollama provider is real (stdlib HTTP) — **LOCAL_VERIFIED** (`gemma3:4b` inference
  round-trips); Ollama-down → HTTP 200 `NOT_RUNNING`, no crash; deterministic task
  → `python` no model call; local_light task → local model (premium only in the
  fallback list); premium task → premium cloud or honest local fallback;
  **LOCAL_ONLY + local down → clear failure, 0 cloud calls**; schema-invalid local
  output escalates and succeeds on the next engine; cost preview media = `UNKNOWN`
  (never fabricated), local = "LOCAL PROCESSING · API ₩0", OFF platform adds 0
  cost; routing telemetry + `ModelPerformance` memory (UNKNOWN < 8 samples);
  benchmark writes performance rows; **Content Library discovers a pre-governance
  legacy campaign** (LEGACY badge, no crash, real MP4 streams, revenue/analytics/
  history populate); demo render flagged `is_demo`; add-platform-later adds only
  the new platform (409 on an already-selected one); server pagination; workspace
  scoping. Migration `0010_phase8` applied. Frontend `tsc` + `next build` clean
  (~24 routes incl. `/create`, `/library`, `/setup`, `/settings/local-ai`,
  `/calendar`, `/system`). 0 new dependencies. Full regression: see the latest run.
- **Cross-Phase Intelligence Upgrade**: `tests/intel/` = **66 passed** (URL learning /
  security / injection / LEARN_ONLY guard / dataset / distillation / composer /
  platform selection / API / governance-integration) + **1 integration E2E**
  (`test_e2e_intel.py`: URL learn + CREATE_AND_LEARN + DISABLED skips generation +
  GENERATE_ONLY skips the job + YouTube/TikTok mock-publish). Coverage of the
  completion gate: LEARN_ONLY creates no Campaign/Asset/MediaTask/PublishJob;
  REFERENCE_ONLY writes no dataset/prompt; SSRF + prompt-injection URLs blocked and
  reported, never executed; single-reference blueprint stuck at EXPERIMENTAL;
  system cannot auto-PROMOTE; verbatim source text absent from blueprints/skills;
  DISABLED platform = 0 content + 0 jobs + 0 API calls; GENERATE_ONLY = content, 0
  jobs; queued TikTok job blocked after user turns TikTok off (`PLATFORM_DESELECTED`);
  re-enable reuses assets, no duplicate job; Autopilot can't re-enable a user-
  disabled platform; cost preview `PRICING_UNKNOWN`; generated≈reference →
  governance `FIX_REQUIRED`; multi-brand isolation of references/datasets/prompts.
  0 new dependencies. Migration `0009_intelligence` applied (head `0009`).
  Frontend `tsc` + `next build` clean (17 routes incl. `/compose`, `/learn-studio`,
  `/references`, `/prompt-lab`). Secret scan clean. Full regression: see the latest run.
- **Phase 7 (Content Governance)**: `tests/governance/` = **46 passed** (28 units +
  13 gate + 5 e2e). Full regression **311 collected** — green after one deterministic
  fix (`tests/ops/test_backup_restore.py` migration-revision pin `0007`→`0008`
  following migration `0008_governance`; the only breakage from the phase). Coverage:
  UNKNOWN_RIGHTS blocked from FULL_AUTO (hard) / HUMAN_REVIEW in manual; expired
  licence + scheduled-after-expiry BLOCK; watermark BLOCK; CC-BY attribution
  FIX→package→pass; AI PLATFORM_FIELD_REQUIRED FIX→set-field→pass; cloned-voice
  no-consent BLOCK (hard); synthetic public-figure endorsement BLOCK; script↔chart
  number mismatch BLOCK (hard); news-media asset ≠ fact right → not ALLOW; music
  allowed on YouTube but PLATFORM_RESTRICTED on TikTok; stale policy → review; clean
  AI+music+disclosure → ALLOW_WITH_ATTRIBUTION; **direct `run_publish_job` on an
  UNKNOWN_RIGHTS campaign → job BLOCKED, never reaches the platform**; autopilot
  post-render gate not-publishable; RightsManifest asset list + render sha256 match;
  rights rows workspace-scoped. Deterministic (no LLM verdict). Secret scan clean.
  Frontend `tsc` + `next build` clean (13 routes incl. `/governance`).
- Phase 5 tests: **44 passed** (`tests/ops/`: 18 unit + backup/restore + recovery + flags/failures + security). Real pg_dump→verify→restore round-trip into `acf_restore_test` (migration_revision `0006_production`).
- GitHub Audit: 3 low-risk code improvements applied (D60) + `tests/test_agents_common.py` (7 cases); full regression re-run green after the changes.
- Advanced Video Studio: `app/video/` (22 deterministic modules + `adapters/` CODE_READY + `ffmpeg_probe.py`); wired additively into `media_nodes.scene_plan` (`creative_plan`) and `media_qa` (`video_qa` incl. Creative QA V2 + Technical QA V2 + cut rhythm + repair plan); `image_motion` cinematic-motion delegation + `subtitles.write_ass_kinetic`. `tests/video/` = 40. `/campaigns/[id]/studio` frontend page (tsc + build clean).
- Agent core (continuation): `app/agents/{research,factcheck,hooks}.py` + `tests/test_agent_core_upgrades.py` (11). No-op on mock data by design; media/agent suites (40+40) green.
- Full regression (all phases): see the latest test report / run.
- Phase 4 tests: **26 passed** (`tests/autopilot/`: 12 unit + 6 scoring + 8 e2e). Full suite (all 5 phases) run separately.
- Phase 3 regression after the `embedding.py` particle-aware improvement: 16/16.
- Frontend `tsc` clean; `next build` clean (9 routes incl. `/autopilot`).
- `docker compose config` OK; Alembic head `0005_autopilot`.
- Phase 4 coverage: trend capability honesty; velocity/trend-status; risk classifier (ELECTION/MEDICAL escalate); natural-content feasibility; hard rules (AI blocked, user allowed) via function + API 403 + config versioning; opportunity scoring inverts bad dims; **PROFIT objective prefers the efficient candidate, VIEWS prefers the viral one, ranking changes by objective**; duplicate guard vs recent publishes; topic fatigue from Phase 3 memory; portfolio **diversity guard** + **hard budget limit**; **SHADOW produces zero content/publish**; **full FULL_AUTO mock e2e** (scan→candidate→score→select→campaign(1-A SUCCESS)→media(1-B)→publish jobs→SCHEDULED, decision log); **crash recovery** (resume → no duplicate campaign); **dead-trend pre-publish recheck** cancels an expired BREAKING trend; **CRITICAL risk → job mode MANUAL**; **all trend sources down → 0 candidates, graceful**; **watchdog pauses on post-limit breach**; **emergency stop** halts runs + candidates + jobs and refuses the next run.

## Pending / Next Step
- **NEXT: Phase 9** — do NOT start unprompted (Phase 8 §101 STOP).
- **Phase 8 follow-ups (DESIGN_ONLY / OPTIONAL):** browser E2E via Playwright
  (project-scoped dep, pending approval); `start-local.ps1` assumes a
  `docker-compose.yml` at repo root and a `.venv` — adjust per deployment; real
  cloud pricing verification before enabling a paid provider (D10/D91);
  per-scene editor + natural-language edit `ImpactAnalyzer` UI (backend
  Smart-Rerender exists, the NL-edit surface is DESIGN_ONLY); load-test fixture
  (`2 ws / 10 brands / 50 channels / 1000 campaigns`) + measured dashboard
  benchmarks (numbers not claimed until measured).
- **Intelligence Upgrade follow-ups (DESIGN_ONLY / OPTIONAL):** enable the
  `BrowserFetchAdapter` with an approved headless-browser dependency (Playwright);
  real frame-level video CV (shot detection / scale / motion) as an adapter — today
  everything not in the supplied profile is `UNKNOWN`; PDF text extraction (no
  parser dependency yet — PDFs are `LIMITED`); Channel/Brand/Workspace default
  platform selections surfaced in the sidebar; batch learning worker/queue for
  100+ URLs (architecture supports it; runs inline today); watchlist auto-ingest
  scheduler; recompute blueprint/skill confidence on reference removal.
- **Phase 7 follow-ups (DESIGN_ONLY / OPTIONAL):** live per-platform policy fetch +
  diff + re-verification job; region ad-disclosure law tables beyond KR 표시광고법
  (FTC, EU AI Act transparency); C2PA / Content Credentials signing (needs a
  signing identity + a verifying platform — `AI_DISCLOSURE.md`); heavy perceptual /
  scene-level video fingerprint adapter (videohash / PDQ); CV logo-face-OCR-PII
  adapter; external web re-upload / duplication check; realism classifier for
  "photoreal vs stylised" AI media; wiring the AI-disclosure platform field into a
  real publish call (blocked on real publisher credentials — Phase 2).
- **NEXT (was): Phase 6** — done 2026-09-01 (see Prior — PHASE 6 complete).
- **Audit follow-ups (from `BEST_SKILL_MATRIX.md`, none started):** RECOMMENDED —
  research first-pass sub-query fan-out + `PageReader`(trafilatura) provider;
  `textstat` + lexical-diversity + semantic-repeat naturalness signals; ASS `\k`
  karaoke captions; unify retry on `tenacity`; Mem0-style memory retrieval fusion;
  `SkillRegistry`/`SkillRouter` (spec §26–§29). RECOMMENDED_FOR_LATER — real
  embeddings via `EmbeddingProvider`+`model2vec` (D61, highest leverage); finish
  `WhisperXAlignmentProvider`; Kokoro/Piper `TTSProvider`; `pybandits` experiment
  engine; `ruptures`/STL trend signals + calibrate `scoring.py` weights; LangGraph
  0.2.60→0.6.x (`interrupt()` HITL, node cache).
- Operator go-live work (Phase 5 hand-off, all NEEDS_PRODUCTION_ENVIRONMENT): provision real Postgres + WAL/PITR + off-site/S3 backups; supply `SECRET_KEY`/`ACF_MASTER_KEY`/DB+Redis passwords via a secret store; real domain + TLS (Caddy `proxy` profile or upstream); set `CORS_ALLOW_ORIGINS`/`TRUSTED_HOSTS`; auth boundary in front of `/api/ops/*` + `/admin`; register a real alert notifier. See `docs/DEPLOYMENT_CHECKLIST.md`.
- Real trend sources: supply per-source credentials → wire `HttpTrendClient` + adapters (YouTube mostPopular, Naver DataLab, an approved Google-Trends proxy, web/news search); `TrendSource.auth_status` then moves past mock.

## Known Issues / Limitations
- **No real trend/platform credentials → every trend source is MOCK.** Deterministic feature-driven catalogue; never reported as real. Real restrictions in `docs/TREND_CAPABILITIES.md` (Google Trends alpha is approval-gated, TikTok/Threads have no discovery API, X trends need a paid tier).
- Topic clustering uses the cheap particle-aware hashing embedding — coarse; swap for a real `EmbeddingProvider` before scale.
- Opportunity "confidence" and calibration are heuristics; the experiment engine is `SEQUENTIAL`, not randomised A/B — all labelled.
- FULL_AUTO in tests runs with `DRY_RUN=true` — publish jobs are created but not sent (Phase 2 already gates real publishing behind credentials).
- Autopilot Celery beat cadence is interval-based (daily), not a wall-clock 05:30 schedule — all cadences are config values.
- Full test suite is now long (~15–20 min): media, publishing-engine and autopilot-e2e tests each build full Phase 1-B campaigns.
- Frontend has no automated tests (typecheck + build only).
- **Phase 5 production items depending on infrastructure that was never supplied (prod server, domain, SSL cert, cloud credential, SNS prod credential) are CODE READY / LOCAL-STAGING VERIFIED / NEEDS_PRODUCTION_ENVIRONMENT** — off-site/S3 backup, WAL/PITR, external alert channels, OTel/Sentry export, TLS issuance, log aggregation. Interfaces + compose profiles exist and run locally; not verified live; never reported as PASS. Full list: `docs/PRODUCTION_READINESS.md`.
- `/api/ops/*` and `/admin` have no built-in auth — they rely on the deployment's front door (`DECISIONS.md` D57).
- Backups land on the app volume only (local); `backup_destination` has an unused `s3` slot.
- **Phase 8**: Local AI needs Ollama running + `OLLAMA_ENABLED=true`; when it's
  off the router uses cloud (or fails clearly under LOCAL_ONLY). Cloud model
  prices are `ESTIMATED` (public list) until an operator verifies them. Media
  cost is always `UNKNOWN` while providers are MOCK. `ModelPerformance` strength
  is `UNKNOWN` until 8+ real observations. Browser E2E is not wired (no new dep);
  frontend is covered by API + `test_phase8_e2e.py`. Full regression is run in
  two halves in this environment (a single 20-min job was being killed mid-run).
- **Intelligence Upgrade**: JS-rendered pages need `browser_fetch_enabled` + an
  approved headless browser (off by default, D67). Video deep-analysis works only
  from a caller-supplied structured profile — unmeasurable fields are `UNKNOWN`,
  never fabricated (real CV is an OPTIONAL adapter). PDFs are `LIMITED` (no parser
  dependency). Batch learning runs inline (worker/queue is DESIGN_ONLY). Text
  similarity / dedup use the cheap 24-dim hash + simhash (D61 ceiling). Learned
  prompts never auto-reach production (`AUTO_PROMOTE_LEARNED_PROMPTS=false`).
- **Phase 7 governance**: platform policy rows are **fixtures** modelling each
  platform's published rules (`source_reference` + `last_verified_at`); real
  current-policy verification is `NEEDS_PRODUCTION_ENVIRONMENT` /
  `LEGAL_REVIEW_REQUIRED`. Text-similarity embedding is the cheap 24-dim hash
  (weak far-paraphrase; D61). pHash is aHash+dHash only; logo/face/OCR/PII CV is
  an OPTIONAL adapter — absent ⇒ route to review, never a faked pass. No C2PA /
  Content Credentials (D81). "Fair use / 인용" is never asserted by the system —
  always `LEGAL_REVIEW_REQUIRED`. Publishers are still MOCK, so the AI-disclosure
  platform field is modelled, not sent.

## Important Constraints (never drop in any phase)
Security · Validation · Error Handling · Testing · Checkpoint · Retry · Idempotency / **no duplicate campaigns or posts** · Official API first, **no consent/verification/approval bypass, no scraping platforms without a public API** · Unsupported metric ⇒ null/UNAVAILABLE, never 0 · One viral post ⇒ not a STRONG memory; correlation ≠ causation · Memory/Opportunity are guidance, never fact · **The AI never edits source code — only weights, memory, recipes, prompt selection, thresholds, experiments, calibration** · **HARD RULES (budgets, post limits, blocked topics, compliance floor, emergency stop) are code-enforced and AI-immutable** · **Sunk cost never forces publishing a dead trend** · DB Integrity · Platform Policy · Copyright/Originality · Budget Guard (LLM + media + publishing + autopilot daily/monthly HARD budget) · AI-content disclosure is never stripped.
