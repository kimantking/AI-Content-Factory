# MASTER IMPLEMENTATION AUDIT — Phase 1 ~ Phase 8

> Audit date: 2026-09-01 · Method: code as source of truth + targeted runtime
> probes (not a full re-run — Phase 8 full regression already passed 434/434).
> No fixes applied (audit freeze, spec §125). Companion files:
> `FEATURE_COVERAGE_MATRIX.md`, `PRODUCTION_VERIFICATION_MATRIX.md`,
> `TECH_DEBT_AND_GAPS.md`, `artifacts/master_audit.json`.

## Structural facts (verified)

| | value | how verified |
|---|---|---|
| Migration head | `0010_phase8` (single head, no branches, chain 0001→0010) | `alembic heads` / `alembic current` |
| ORM tables | 97, **all present in DB**, **0 column mismatches** | `Base.metadata` vs `inspect(engine)` cross-check |
| Non-ORM DB tables | `checkpoint_*` ×4 (LangGraph Postgres checkpointer — intentionally not Alembic-managed, D6) | schema diff |
| Live API routes | 162, all router-registered | `app.routes` enumeration |
| Frontend routes | 23 `page.tsx` | `find app -name page.tsx` |
| Tests | **434** at audit → **449** (AUDIT-P8-001 repair, +15) → **486** (MASTER MEDIUM GAP REPAIR, +37); full regression **486 passed / 0 failed / 0 errors** | 5-batch JUnit XML |
| Backend deps | 22 (`requirements.txt`) — **0 added in Phases 6/7/8/intel**; no `ollama` pkg, no `playwright` | file read |
| Frontend deps | `next` / `react` / `react-dom` + std dev tooling — **0 added** | `package.json` |

## Static hygiene sweep

- **Stub / TODO / NotImplemented in `app/`**: 2 hits. Both legitimate —
  `media/compliance.py:58` is a regex that *detects* "TODO"/"lorem ipsum"
  placeholder text in generated content (a QA check); `media/word_timing.py:60`
  is the scaffolded **OPTIONAL** `WhisperXAlignmentProvider` (Design Amendment
  §11) with a working `EstimatorAlignmentProvider` fallback. → no hidden stubs.
- **Silent failure (`except …: pass/continue`)**: 16 blocks, all **narrow typed
  exceptions** (`ValueError`/`KeyError`/`OSError`/`TypeError`/`ProviderError`
  version-probe / `OptionalSkillUnavailable`). Contexts: parse fallbacks, font/
  file probing, optional-skill iteration, cache miss, backup dir cleanup, Ollama
  version metadata. **None in a critical decision path.** Risk: LOW.
- **Fake success**: none found. `job.status = PUBLISHED` is set only from a
  publisher-adapter `result.status` (mock adapter ⇒ MOCK_VERIFIED). `camp.status
  = "SUCCESS"` is gated on real QA `passed`. No unconditional
  `published=True`/`connected=True`.
- **Dead UI**: none. No empty `onClick`, no `console.log`-only handlers, no
  `alert()`-only, no `// TODO` handlers.
- **Frontend fake data**: none shown as production. `campaigns/[id]/media`
  explicitly labels `"아직 없음 (mock = $0)"`; `page.tsx` `FALLBACK_*` are used
  only when `getConfig()` fails; `mockConnect` calls a real, honestly-named
  `/api/publishing/accounts/{p}/mock-connect` endpoint.
- **Analytics zero-coercion (§16)**: none. `AnalyticsSnapshot` metrics are
  nullable with the model comment "None means genuinely unknown, never coerced to
  0"; grep for `views ... or 0` in `app/analytics/` returns nothing.

## Agent runtime (§7)

LangGraph is the **sole** agent runtime (`app/agents/graph.py`,
`media_graph.py`). No `crewai` / `metagpt` / `autogen` imports anywhere. Concepts
borrowed, libraries not (D1). → IMPLEMENTED.

## Worker / queue (§103–§105)

~16 Celery tasks in `app/tasks.py`; every one has a producer (API route, beat, or
DLQ retry). **No orphan tasks, no orphan enqueues.** The Phase-8 URL-learning job
(`intel.engine.run_learning_job`) and the Model-Router call (`ai_router.run_routed`)
run **inline in the request**, not on a worker — this is the documented
DESIGN_ONLY batch-worker follow-up (intel upgrade §CF), not a broken job.

## Critical invariants (§123) — runtime evidence

26 targeted probe tests re-run this audit, all pass:

| invariant | evidence |
|---|---|
| LEARN_ONLY → 0 production | `tests/intel/test_learn_only.py` (5): no Campaign/Asset/MediaTask/PublishJob rows |
| Platform OFF → 0 generation, 0 job, 0 API | `test_platform_selection.py::test_generation_skip_no_jobs_for_off_platform`, `::test_all_off_selection` |
| Queue OFF race → 0 remote call | `::test_publisher_gate_blocks_deselected_platform_race` (job → BLOCKED, no `remote_post_id`) |
| Autopilot can't re-enable user-OFF platform | `::test_autopilot_cannot_reenable_user_disabled_platform` |
| Re-enable reuses assets, 0 dup job | `::test_reenable_reuses_assets_no_duplicate_job` |
| LOCAL_ONLY → 0 cloud calls | `tests/ai_router/test_execute.py::test_local_only_never_calls_cloud_even_on_local_failure` |
| cheap task → 0 premium calls | `::test_cheap_task_never_calls_premium` |
| Governance BLOCK → 0 remote publish | `tests/governance/test_e2e.py::test_publisher_cannot_publish_unknown_rights` |
| Cross-brand → 0 data leak | `tests/intel/test_isolation_and_rights.py` (3), `test_e2e.py::test_rights_data_is_workspace_scoped` |
| Viewer → protected write 403 | `tests/mb/test_auth_rbac.py::test_viewer_cannot_write_editor_can` |
| Budget hard limit under concurrency | `tests/mb/test_budget.py::test_concurrent_reservations_cannot_exceed_hard_limit` |
| Single-scene repair → 1 scene only | `tests/video/test_engines_v2.py::test_rerender_broll_change_rebuilds_one_scene_and_composition`, `tests/media/test_integration.py::test_scene_regeneration_touches_only_one_scene` |
| Platform add later → 0 unrelated regen | `tests/library/test_content_library.py::test_add_platform_later_only_adds_new` |
| Ollama real local inference | `tests/ai_router/test_ollama.py` (4) + LIVE probe: `gemma3:4b` → `{"label":"NEWS"}` in 2.3 s |

## THE gap — AUDIT-P8-001 — **RESOLVED 2026-09-01** (see `TECH_DEBT_AND_GAPS.md`)

Originally: the Model Router + Ollama provider were a fully-built, tested,
LOCAL_VERIFIED subsystem but NOT wired into the agent content-production pipeline
(`agents/nodes.py` / `agents/media_nodes.py` called `get_llm_provider().complete()`
directly).

**Repair applied** (no schema, no new dependency): new
`app/agents/model_gateway.py` — `routed_complete(...)` is the single door every
production agent LLM call goes through. It maps the agent task to a router
`(agent_type, task_type)`, runs `ai_router.run_routed` (select → provider →
structured-output validation → bounded escalation → fallback chain → telemetry +
cost), passes the *original* task label as `provider_task`, threads
`campaign_id`/`workspace_id`, and on any router error falls back to the legacy
provider (the one sanctioned EXPLICIT_EXCEPTION). Swapped chokepoints:
`nodes.py::_run_llm` (research/fact_check/strategy/hook/script/script_qa) and
`media_nodes.py::_llm_json` (platform_adapt/scene_plan/edit_decision); the
natural-writing rewrite uses a `GatewayLLM` shim; `get_llm_provider` imports
removed from both agent modules. Support changes: a MOCK-MODE `mock` registry
entry + `_provider_for("mock")` so a routed decision + telemetry are produced in
dev/test without a key; `RoutedResult` carries token counts + reason.

A follow-up `§19` sweep found one more UNROUTED production LLM call —
`autopilot/pipeline.py::_llm_json` (topic-angle extraction) — now also routed
through the gateway (`agent_name="Strategist"`, `topic_extract` → `basic_extraction`
/ local_light). The static bypass guard covers all three modules.

**Runtime evidence** (`tests/agents/test_model_gateway.py`, 15 tests, all pass):
- static bypass guard — **0** direct provider calls/imports in
  `agents/nodes.py`, `agents/media_nodes.py`, `autopilot/pipeline.py`;
- a full Research→Fact→Strategy→Hook→Script run writes **≥4 `ModelRoutingEvent`**
  rows spanning **`standard` + `premium`** tiers;
- a standard/light agent task routes to **`gemma3:4b` (provider=ollama, real
  local call)** with **0** premium events;
- per-agent tier policy verified (research/fact/platform_adapt/scene_plan →
  standard; strategy/hook/script → premium);
- bad local JSON → escalates to the next engine (no loop);
- **LOCAL_ONLY + local failure → 0 cloud calls** (controlled failure);
- ALLOW_CLOUD_FALLBACK + key → local failure falls back to a cloud model;
- a gateway call records the campaign + workspace id.

**Full regression after the repair (2026-09-01): 449 passed / 0 failed / 0 errors
/ 0 skipped** (baseline 434 + 15 new gateway tests). Run in 7 sub-batches because
this environment kills jobs longer than ~13 min; per-batch JUnit XML: agents 15,
ai_router+autopilot 61, 10 root test files 46, phase8_e2e+intel 75,
governance+mb 88, library+media+analytics 49, ops+publishing+video 115.

PromptComposer / LearnedSkills were then merged into the agent system prompt in
the MASTER MEDIUM GAP REPAIR — see "MEDIUM gap resolution (2026-09-01, D95)" below
(AUDIT-P8-006 RESOLVED).

## Executive summary

| bucket | count |
|---|---|
| Requirements inventoried | 132 (`FEATURE_COVERAGE_MATRIX.md`) |
| IMPLEMENTED + TESTED | 111 (+7 — the MEDIUM-gap features now wired + tested) |
| IMPLEMENTED + LOCAL_VERIFIED | 3 (Ollama provider, provider graceful-degradation, live inference) |
| IMPLEMENTED + MOCK_VERIFIED only | 14 (all real-provider / real-platform adapters) |
| PARTIAL | 0 (was 5 — AUDIT-P8-001 + all 7 MEDIUM gaps resolved) |
| DESIGN_ONLY | 3 (Reposition-strategy LLM, CreativeRecipe→production, C2PA — all correctly labelled, none in an audited gap) |
| NEEDS_CREDENTIALS | 10 |
| NEEDS_PRODUCTION_ENVIRONMENT | 8 |
| NOT_IMPLEMENTED | 0 |
| Critical gaps | 0 |
| High gaps | **0** (AUDIT-P8-001 RESOLVED 2026-09-01) |
| Medium gaps | **0** (all 7 RESOLVED 2026-09-01 — MASTER MEDIUM GAP REPAIR, D95) |
| Low gaps | 5 (unchanged) |

**`PHASE_1_8_FUNCTIONAL_BASELINE_LOCKED` — 2026-09-01.** 0 CRITICAL / 0 HIGH / 0
MEDIUM implementation gaps; full regression 486 passed / 0 failed. Production
verification (credentials + environment) stays PENDING and is *not* an
implementation gap.

## Phase status (one line each)

- **Phase 1** — IMPLEMENTED + TESTED. Research→Fact→Strategy→Hook→Script is one
  LangGraph flow with Postgres checkpointing, retry taxonomy, cost logging.
- **Phase 2** — IMPLEMENTED + MOCK_VERIFIED. 10-platform capability registry,
  PublishJob idempotency/retry/scheduler/reconcile, Publisher gate. Real platform
  adapters NEEDS_CREDENTIALS.
- **Phase 3** — IMPLEMENTED + MOCK_VERIFIED. Capability-gated analytics (null, not
  0), feature store, performance scores, evidence-based learning, memory,
  experiments. Real analytics APIs NEEDS_CREDENTIALS.
- **Phase 4** — IMPLEMENTED + MOCK_VERIFIED. 10 trend providers (mock),
  two-stage opportunity scorer, portfolio, autopilot bridge + recheck + watchdog
  + emergency stop. Real trend sources NEEDS_CREDENTIALS.
- **Phase 5** — IMPLEMENTED + LOCAL/STAGING VERIFIED. Docker/compose, health,
  backup→verify→restore round-trip, DLQ, leases, rate-limit, redaction, SSRF.
  Prod server / domain / TLS / off-site backup / external alerts
  NEEDS_PRODUCTION_ENVIRONMENT.
- **Phase 6** — IMPLEMENTED + TESTED. Auth + RBAC (backend 403), tenant +
  credential isolation, transactional hierarchical budget, deterministic Channel/
  Portfolio managers, monetization guards. Long-tail sidebar/scheduler was
  DESIGN_ONLY → partially delivered in Phase 8 (calendar).
- **Phase 7** — IMPLEMENTED + TESTED. Deterministic governance gate (no LLM
  verdict), rights ledger, licence/policy registries (policy rows are FIXTURES),
  AI disclosure (never stripped), originality incl. cross-brand + vs-learned-
  references, claims, wired into Publisher + Autopilot, hard blocks unclearable.
- **Cross-Phase Intelligence Upgrade** — IMPLEMENTED + TESTED. URL learning
  (untrusted + SSRF + injection guards), reference dataset + curator, prompt
  distillation (no auto-promote, single-source guard), learned skills, prompt
  composer, 4-state execution mode, 3-state SNS selection.
- **Phase 8** — IMPLEMENTED + TESTED. Beginner UX, Content Library (discovers
  legacy content, streams real MP4), Ollama provider (LOCAL_VERIFIED), Model
  Registry + Router + escalation + telemetry + benchmark, Cost Estimator
  (KNOWN/ESTIMATED/UNKNOWN, no fake prices). **AUDIT-P8-001 RESOLVED** — every
  production agent LLM call now goes through `app/agents/model_gateway.py` →
  `ai_router.run_routed`; a light agent task provably routes to `gemma3:4b`, and a
  full campaign emits routing telemetry across standard + premium tiers.

## Final verdict  (updated 2026-09-01 after the MASTER MEDIUM GAP REPAIR)

**B. PHASE 1–8 FUNCTIONALLY COMPLETE, PRODUCTION VERIFICATION PENDING.**
`PHASE_1_8_FUNCTIONAL_BASELINE_LOCKED` — 0 CRITICAL / 0 HIGH / **0 MEDIUM**
implementation gaps; full regression **486 passed / 0 failed**.

Every critical invariant holds with runtime evidence, schema is clean (97 ORM
tables, 0 mismatches, single migration head, no destructive DDL), there is no
dead / stub / fake-success code in any critical path, dependency discipline held
(0 new deps across Phases 6–8, and the AUDIT-P8-001 repair added none). The sole
HIGH gap — the Model Router / Ollama not being on the agent production path — has
been closed: every production agent LLM call now goes through
`app/agents/model_gateway.py` → `ai_router.run_routed`; a light agent task
provably routes to `gemma3:4b`, a full campaign emits routing telemetry across
`standard` + `premium` tiers, escalation and the LOCAL_ONLY invariant hold on the
real path, and a static guard forbids re-introducing a direct provider call.

Remaining gaps are 0 CRITICAL, 0 HIGH, **0 MEDIUM**, 5 LOW — none blocking. All 7
MEDIUM items were resolved in the MASTER MEDIUM GAP REPAIR (2026-09-01, D95):
PromptComposer on the agent path (P8-006), router auto-tune from telemetry
(P8-005), unified global search (P8-003), NL-edit + impact preview backend
(P8-002), Setup Wizard server persistence (P8-004), cross-channel capacity planner
(P6-001), human-in-the-loop policy verification (P7-001) — each with targeted
tests; 1 additive migration (`0011_medium_repair`), 0 new dependencies. The LOW
items (5) are cosmetic and unchanged.

**Can proceed to Phase 9: YES.**

**Production verification pending** (unchanged — needs real credentials /
environment, not implementation): Anthropic / Tavily / media-provider keys; SNS
OAuth + app review; analytics scopes; revenue API permissions; real off-site
backup + WAL/PITR; domain + TLS; external monitoring / alert delivery. These stay
`NEEDS_CREDENTIALS` / `NEEDS_PRODUCTION_ENVIRONMENT` and are not a barrier to
Phase 9 development.

### Verdict history
- 2026-09-01 (initial audit): **C** — remaining implementation gaps; blocking
  gap AUDIT-P8-001; cannot proceed to Phase 9.
- 2026-09-01 (AUDIT-P8-001 repair): **B** — functionally complete; can proceed
  to Phase 9. Remaining: 7 MEDIUM, 5 LOW.
- 2026-09-01 (MASTER MEDIUM GAP REPAIR, D95): **B** held — all 7 MEDIUM resolved,
  `PHASE_1_8_FUNCTIONAL_BASELINE_LOCKED`; 0 CRITICAL / 0 HIGH / 0 MEDIUM
  implementation gaps, 5 LOW; full regression 486 passed / 0 failed. Verdict stays
  B (not A) because production verification (credentials / environment) is still
  pending.

### MEDIUM gap resolution (2026-09-01, D95)

| Gap | Before | Fix (files) | Tests | Status |
|---|---|---|---|---|
| AUDIT-P8-006 | composer not called on the agent path | `app/agents/model_gateway.py::_compose_system`; `app/intel/composer.py` (brand filter + `disabled_ids`); `ModelRoutingEvent.prompt_lineage` (mig `0011`) | `tests/agents/test_prompt_composer_wiring.py` 11 | RESOLVED |
| AUDIT-P8-005 | `select()` ignored `ModelPerformance` | `app/ai_router/router.py::_apply_performance` (+ `db=` thread from `run_routed`) | `tests/ai_router/test_autotune.py` 3 | RESOLVED |
| AUDIT-P8-003 | search = topic + script only | `app/library/search.py`; `GET /api/search` | `tests/library/test_global_search.py` 5 | RESOLVED |
| AUDIT-P8-002 | no NL→EditRequest / impact preview | `app/edit/nl_to_request.py`, `scene_io.py`; `POST /api/library/{id}/edit-plan` | `tests/edit/test_nl_to_request.py` 5 | RESOLVED (panel UI = LOW) |
| AUDIT-P8-004 | wizard localStorage only | `frontend/lib/api.ts::finishSetup`, `app/setup/page.tsx`; `create_workspace`/`create_brand` now commit | `tests/mb/test_setup_wizard_persistence.py` 2 + `tsc` | RESOLVED |
| AUDIT-P6-001 | capacity planner DESIGN_ONLY | `app/autopilot/capacity.py`; controller cap; `GET /api/publishing/calendar/capacity` | `tests/autopilot/test_capacity.py` 5 | RESOLVED |
| AUDIT-P7-001 | policy rows = fixtures, no verify job | `app/governance/policy_verify.py`; `GET/POST /api/policy/verif*` | `tests/governance/test_policy_verify.py` 6 | RESOLVED (live *fetch* stays NEEDS_PRODUCTION_ENVIRONMENT) |
