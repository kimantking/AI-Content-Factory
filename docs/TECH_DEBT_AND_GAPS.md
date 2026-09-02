# TECH DEBT & GAPS — Master Audit (Phase 1 ~ Phase 8)

> Frozen 2026-09-01. **No fixes applied** (audit integrity, spec §125). Each gap:
> ID · Severity · Feature · Current · Expected · Evidence · Why it matters ·
> Recommended fix. Severities: CRITICAL / HIGH / MEDIUM / LOW.

## CRITICAL — 0

None. No governance bypass, no tenant-data leak, no "SNS OFF but publishes",
no "LEARN_ONLY but produces", no secret exposure, no fake production success.
All ten critical invariants (§123) hold with runtime evidence.

## HIGH — 0  (AUDIT-P8-001 RESOLVED 2026-09-01)

### AUDIT-P8-001 — Model Router & Ollama wired into the agent production path — RESOLVED
- **Was**: HIGH — agent nodes called `get_llm_provider().complete()` directly, so
  the router / per-agent policy / escalation / local Ollama were never exercised
  by a real campaign.
- **Fix applied** (no schema, no new dependency): new `app/agents/model_gateway.py`
  `routed_complete(...)` maps the agent task -> router `(agent_type, task_type)`,
  runs `ai_router.run_routed` (select -> provider -> structured-output validation
  -> bounded escalation -> fallback chain -> telemetry), passes the ORIGINAL task
  label as `provider_task`, threads `campaign_id`/`workspace_id`, and falls back
  to the legacy provider on any router error (the one sanctioned
  EXPLICIT_EXCEPTION). Both chokepoints swapped: `nodes.py::_run_llm` and
  `media_nodes.py::_llm_json`; the natural-writing rewrite uses a `GatewayLLM`
  shim; `get_llm_provider` imports removed from both agent modules. Router gained
  a MOCK-MODE `mock` registry entry (+`_provider_for` handling); `RoutedResult`
  carries `input_tokens`/`output_tokens`/`reason`.
- **Evidence** (`tests/agents/test_model_gateway.py`, all pass): static bypass
  guard (0 direct provider calls/imports in the two agent modules); a full
  Research->Fact->Strategy->Hook->Script run writes >=4 `ModelRoutingEvent` rows
  spanning `standard` + `premium` tiers; a standard/light agent task routes to
  **`gemma3:4b` (provider=ollama, real local call)** with 0 premium events;
  agent-policy tier mapping verified; bad local JSON escalates (no loop);
  LOCAL_ONLY + local failure -> 0 cloud calls; ALLOW_CLOUD_FALLBACK + key ->
  local failure falls back to cloud; a gateway call records campaign+workspace id.
- **Not covered here** (out of scope for "AUDIT-P8-001 ONLY"): PromptComposer /
  LearnedSkills still not in the agent path -> AUDIT-P8-006 (MEDIUM).

### (original write-up, kept for the record) AUDIT-P8-001 — Model Router & Ollama not wired into the agent production path
- **Severity**: HIGH
- **Feature**: Phase 8 goal #4 — "작업별 최적 모델 자동 선택 Model Router" + local
  AI doing light tasks during content production.
- **Current**: `app/agents/nodes.py` (research/fact/strategy/hook/script) and
  `app/agents/media_nodes.py` (scene plan …) call `get_llm_provider().complete()`
  directly. `get_llm_provider()` returns Mock or Anthropic by config — **never
  Ollama, never via the router**. `ai_router.run_routed` is reachable only from
  `routes_ai.py` (preview/benchmark), `benchmark.py`, and `cost.py` (the cost
  estimate does genuinely route — the one real use).
- **Expected**: agent nodes obtain their model via `ModelRouter.select(...)` /
  `run_routed(...)`, so classification/tagging/summary run on `gemma3:4b`,
  strategy/hook/script escalate to a premium model, and routing telemetry
  accumulates from real runs.
- **Evidence**: `grep -rn "run_routed|ai_router" app/agents app/intel` → no hits;
  `nodes.py:50 llm = get_llm_provider()`, `media_nodes.py:65 llm = get_llm_provider()`.
- **Why it matters**: the router, registry, escalation, LOCAL_ONLY enforcement,
  per-agent policy and telemetry are all built and tested, but a real campaign
  never exercises them — so the headline Phase 8 capability is not active where it
  was requested. Per spec §5/§66 this is a defined PARTIAL, not IMPLEMENTED.
- **Recommended fix** (small, no schema/dep change): add a thin
  `agents/model_gateway.py::routed_complete(agent_type, task_type, system, user,
  context)` that calls `ai_router.run_routed` and falls back to
  `get_llm_provider().complete()` on any router error; replace the ~2 direct
  `llm.complete(...)` call sites in `nodes.py` / `media_nodes.py`; add
  `campaign_id`/`workspace_id` for telemetry; re-run `tests/` + one E2E asserting
  a routing event per campaign. Same gateway can carry the PromptComposer merge
  (closes IU-COMP-061 / IU-SKILL-062 PARTIAL).

## MEDIUM — 0  (all 7 RESOLVED 2026-09-01 — MASTER MEDIUM GAP REPAIR)

> Phase 1–8 functional baseline **LOCKED** (`PHASE_1_8_FUNCTIONAL_BASELINE_LOCKED`).
> Production verification (credentials / environment) stays PENDING — see the
> matching section below; it is not an implementation gap.

### AUDIT-P8-006 — PromptComposer / LearnedSkills in the agent path — RESOLVED
- **Was**: agent LLM calls routed through `model_gateway` but the gateway never
  called `intel.composer.compose(...)`, so learned skills / blueprints influenced
  nothing at generation time.
- **Fix**: `model_gateway._compose_system()` runs BEFORE routing — Base + Brand +
  Channel + Memory + agent-relevant Learned Skills + Prompt Blueprints, under
  `max_learned_context_tokens`, agent-alias + platform + brand filtered, honouring
  the user "disable" switch (`ReferenceFeedback` verdict BLOCK/NOT_USEFUL/WRONG)
  and the strict production default (only PROMOTED blueprints). Retrieval is
  deterministic DB reads — no extra LLM call (cheap-first). Lineage
  (`prompt_composer_used`, `skill_ids`, `blueprint_ids`, `memory_ids`,
  `prompt_version`, `context_tokens`, `truncated`) is carried on
  `GatewayResponse` and persisted to `ModelRoutingEvent.prompt_lineage`
  (migration `0011_medium_repair`, additive nullable JSON).
- **Evidence**: `tests/agents/test_prompt_composer_wiring.py` (11) — composer used
  on the real agent path; relevant skill injected / irrelevant not; blueprint
  agent + platform + brand-isolation filters; disabled skill excluded; context
  budget enforced + `truncated`; lineage row written; compose-then-gateway order;
  **direct-provider bypass still 0**. `tests/intel/test_composer.py` (5) still green.
- `config.prompt_composer_enabled` (default true) is the master switch.

### AUDIT-P8-005 — Router auto-tune from performance memory — RESOLVED
- **Was**: `ModelPerformance` / `performance_hint` computed + exposed but
  `ModelRouter.select` never consulted them.
- **Fix**: `ModelRouter._apply_performance(db, task_type, cands)` reorders
  candidates by learned strength — proven-STRONG first, proven-WEAK last,
  unmeasured neutral — only when `db` is threaded (from `run_routed`) and
  `model_routing_autotune_enabled` (default true). Still no shift below
  `model_routing_min_sample` (`performance_hint` already drops UNKNOWN rows).
- **Evidence**: `tests/ai_router/test_autotune.py` (3) — WEAK local downranked
  below STRONG cloud after 12 samples; no shift at 3 samples; switch-off keeps
  the default pick.

### AUDIT-P8-003 — Unified global search — RESOLVED
- **Fix**: `app/library/search.py::global_search()` + `GET /api/search` spanning
  Campaign (topic + script body) / PlatformContent (title + caption) / Channel /
  Brand / ReferenceSource / Publication, deterministic exact>prefix>word>substring
  scoring, workspace-scoped, capped result set, `kinds` filter.
- **Evidence**: `tests/library/test_global_search.py` (5) — all six kinds, script-
  body-only match, workspace isolation, ranking, `kinds` filter, short-query reject.

### AUDIT-P8-002 — Natural-language edit + Impact Analyzer — RESOLVED (backend + API)
- **Fix**: `app/edit/nl_to_request.py` — deterministic KR/EN phrase table →
  typed `EditRequest` (`parse_instruction`), pure `apply_edit(scenes, meta, req)`,
  and `impact_of(old, new)` wrapping the existing Smart-Rerender planner into a
  human "this change re-runs X" summary. `POST /api/library/{id}/edit-plan`
  returns the request + impact WITHOUT rendering. `app/edit/scene_io.py` loads a
  campaign's persisted scenes into the planner shape.
- **Evidence**: `tests/edit/test_nl_to_request.py` (5) — multi-clause parse,
  scene-scoped op needs a scene number, subtitle-only reuses AI visuals, b-roll
  swap regenerates only that scene, endpoint.
- **Residual (LOW, tracked)**: the `/library/[id]` scene-editor *panel* UI is not
  built — the deterministic translator + impact API it would call are done.

### AUDIT-P8-004 — Setup Wizard server persistence — RESOLVED
- **Fix**: `frontend/lib/api.ts::finishSetup()` + `app/setup/page.tsx` "설정 완료"
  now POSTs `/api/workspaces` then `/api/brands` (reusing an existing workspace by
  name — safe to re-run), stores the returned ids, then routes to `/create`.
  `create_workspace` / `create_brand` now `db.commit()` so the row survives the
  request session (they previously only `flush()`ed — a latent bug that made the
  wizard's POSTs no-ops).
- **Evidence**: `tests/mb/test_setup_wizard_persistence.py` (2) — workspace +
  brand persist across sessions; wizard reuses an existing workspace by name.
  Frontend `tsc --noEmit` clean.

### AUDIT-P6-001 — Cross-channel capacity planner — RESOLVED
- **Fix**: `app/autopilot/capacity.py` — deterministic `channel_capacity()`
  (`remaining_slots = daily_max_posts - used_today`, `budget_headroom =
  daily_budget_usd - spent_today` from today's Campaigns + PublishJobs + CostLog +
  Asset cost) and `portfolio_capacity()` → `max_new_campaigns`. The Autopilot
  controller caps its selection by this (flag `autopilot_respect_channel_capacity`,
  default true; falls back to `autopilot_daily_content_max` when no channels are
  configured — no regression for single-stream autopilot).
  `GET /api/publishing/calendar/capacity` surfaces the model.
- **Evidence**: `tests/autopilot/test_capacity.py` (5) — slots decrement with
  today's campaigns, budget headroom blocks a channel, portfolio aggregate
  excludes OFF + budget-blocked channels, fallback with no channels, endpoint.

### AUDIT-P7-001 — Platform policy verification (human-in-the-loop) — RESOLVED
- **Fix**: `app/governance/policy_verify.py` — `verification_report()` (the review
  queue: platforms whose rules are stale > `policy_max_age_days` or carry
  `UNKNOWN` status, each labelled `LEGAL_REVIEW_REQUIRED`), `record_verification()`
  (a NAMED reviewer attests a check; bumps `last_verified_at`, optionally updates
  `source_reference`, and flips `UNKNOWN`→`ACTIVE` ONLY on explicit
  `activate_unknown=True`; writes a `GovernanceEvent` for audit), `due_for_review()`
  for a periodic task. No live policy fetch (stays NEEDS_PRODUCTION_ENVIRONMENT).
  `GET /api/policy/verification` + `POST /api/policy/verify`.
- **Evidence**: `tests/governance/test_policy_verify.py` (6) — stale platform in
  queue, UNKNOWN flags review even when fresh, verification bumps timestamp +
  audits, UNKNOWN stays UNKNOWN without explicit attributed activation, named
  reviewer required, endpoints.

## Phase 9 findings (Real-World Validation, 2026-09-01)

### P9-001 — Content Library pagination was O(N) — RESOLVED
- **Was**: `library.service.list_content` materialised + enriched **every**
  matching campaign (7 child-row queries each) before slicing the page — 9.3 s at
  1000 campaigns / 3200 platform contents.
- **Fix**: DB-level `OFFSET/LIMIT` fast path (`_card()` helper) for the common
  case (no `platform`/`content_type`/`governance`/`publish_state` filter, no
  `views`/`revenue`/`profit`/`performance` sort); the full-scan path is retained
  only for those filters/sorts, where every candidate must be materialised.
- **After**: 0.25 s for page 1, flat across deep pages; search 0.27 s; stats
  0.02 s. Test: `tests/phase9/test_content_library_scale.py` (4).
- Severity was MEDIUM (real-world stability). No new dependency, no migration.

### Phase 9 — no other CRITICAL / HIGH / MEDIUM stability gap found
20 concurrent pipelines (0 corruption, pool bounded), LEARN_ONLY 100-ref batch
(0 production), the full failure/recovery matrix, publishing duplicate-safety,
batch-scale security injection, all 12 Phase 1–8 invariants, and a 123-cycle
QUICK_SOAK (no leak) all pass. Full regression **545 / 0 failed**.

## LOW — 5 (+ 2 carry-forward from Phase 9)

| ID | Item | Note |
|---|---|---|
| AUDIT-L-001 | 16 narrow `except …: pass/continue` blocks | all typed + defensive (parse/file-probe/optional-skill/cache/version-metadata); none in a critical decision path. Optionally log at DEBUG. |
| AUDIT-L-002 | WhisperX / VMAF adapters scaffolded | correctly OPTIONAL with working fallbacks; label stays DESIGN_ONLY / NOT_AVAILABLE, never PASS. |
| AUDIT-L-003 | No automated frontend / a11y tests | project has no JS test runner; flows covered by API + `tests/test_phase8_e2e.py`. Browser E2E (Playwright) is OPTIONAL, needs a new dev dep (D67 approval). Now also covers the P8-002 scene-editor panel + P8-004 wizard UI (backend + `tsc` verified). |
| AUDIT-L-004 | Full regression run in batches | a single long background job is killed mid-run in this environment; batches execute every collected test (545). Cosmetic. |
| AUDIT-L-005 | `start-local.ps1` assumptions | assumes repo-root `docker-compose.yml` + `backend/.venv`; adjust per deployment. |
| P9-L-001 | Rendered-browser E2E not run | no JS test runner; Playwright is a new dev dep (D67 approval) + global install disallowed. HTTP-level journey tests + `tsc`/`next build` stand in. `AVAILABLE_NOT_REQUIRED` — add before Phase 10 release. |
| P9-L-002 | FULL_SOAK not run | QUICK_SOAK (180 s / 123 cycles, no leak) passed; FULL_SOAK (~40 min) is `AVAILABLE_NOT_REQUIRED` — recommended before a Phase 10 production release. Also: soak RSS/handle counters unavailable under the MSYS2 Python (heap + pool are the working leak signals). |

## Mock-only vs real (summary)

- **Mock-only (real needs credentials)**: every publishing platform adapter;
  Tavily search; Anthropic LLM; all media providers (image/video/tts/stock/music);
  platform analytics & revenue APIs; trend sources.
- **Local-verified**: Ollama `gemma3:4b` (health + list + real JSON inference);
  backup→restore round-trip; docker-compose config.
- **Deterministic (no provider)**: governance verdicts, originality metrics,
  URL-learning Stage-1/2 + analyzers, cost calc, dedup, model routing decision.

## DESIGN_ONLY (correctly labelled, not IMPLEMENTED)

Reposition strategy LLM · content Template system · capacity planner · NL-edit UI ·
router auto-tune from telemetry · CreativeRecipe → production application ·
batch learning worker/queue (runs inline) · WhisperX/VMAF adapters · C2PA/Content
Credentials · browser-fetch (Playwright) adapter.
