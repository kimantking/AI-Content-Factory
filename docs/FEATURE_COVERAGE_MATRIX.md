# FEATURE COVERAGE MATRIX — Phase 1 ~ Phase 8

> Status taxonomy: IMPLEMENTED · TESTED · LOCAL_VERIFIED · MOCK_VERIFIED ·
> PARTIAL · DESIGN_ONLY · NEEDS_CREDENTIALS · NEEDS_PRODUCTION_ENVIRONMENT ·
> NOT_IMPLEMENTED. Evidence is code path + test; "PASS" is never used alone.

## PART A — Core content pipeline (Phase 1)

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| P1-RES-001 | Research agent + source collection | IMPLEMENTED+TESTED | `app/agents/nodes.py` research nodes; `app/agents/research.py`; `tests/test_agent_core_upgrades.py`, `tests/test_pipeline_integration.py` | real search NEEDS_CREDENTIALS (Tavily) |
| P1-FACT-002 | Fact checker: atomic claims, agreement, confidence, gating | IMPLEMENTED+TESTED | `app/agents/factcheck.py`; fact-gate in `qa_script` (D5) | — |
| P1-STRAT-003 | Strategy agent | IMPLEMENTED+TESTED | `app/agents/nodes.py`; pipeline tests | — |
| P1-HOOK-004 | Hook agent, diversity + exaggeration guard | IMPLEMENTED+TESTED | `app/agents/hooks.py`; `tests/test_agent_core_upgrades.py` | — |
| P1-SCRIPT-005 | Master script + Natural Writing pass + slop score | IMPLEMENTED+TESTED | `app/agents/nodes.py`, `app/naturalness/`; `tests/test_naturalness.py` (6) | — |
| P1-FLOW-006 | One connected flow Research→…→Script | IMPLEMENTED+TESTED | `app/agents/graph.py` StateGraph; `tests/test_pipeline_integration.py` (3) | — |
| P1-RT-007 | LangGraph sole runtime, Postgres checkpoint, resume | IMPLEMENTED+TESTED | `graph.py`, `runner.py`; `tests/test_checkpoint_resume.py` | — |
| P1-RETRY-008 | Retry taxonomy + non-retryable | IMPLEMENTED+TESTED | `app/providers/retry.py`, `errors.py`; `tests/test_retry.py` (4) | — |
| P1-COST-009 | Per-call budget guard + cost logging | IMPLEMENTED+TESTED | `services/cost.py`, `CostLog`; `tests/test_budget_guard.py` (4) | prices are placeholders (D10) |

## PART B — Media / Advanced Video Studio (Phase 1-B + upgrade)

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| P1B-PROV-010 | Image/Video/TTS/Stock/Music provider abstraction | IMPLEMENTED+MOCK_VERIFIED | `app/providers/media/`; `tests/media/` (20) | all providers mock — real NEEDS_CREDENTIALS |
| P1B-FFMPEG-011 | FFmpeg render + validation | IMPLEMENTED+TESTED | `app/media/ffmpeg.py`; `tests/media/test_integration.py` | Remotion is REFERENCE_ONLY (licence, A2) |
| P1B-STORE-012 | Asset storage + hash + provider_mode | IMPLEMENTED+TESTED | `Asset` model; media tests | S3 slot unused (NEEDS_PRODUCTION_ENVIRONMENT) |
| VS-DIR-013 | Video/Story/Retention/Scene/Shot/Visual/B-roll/Motion/Graphics/Voice/Audio/Subtitle directors + Editor | IMPLEMENTED+TESTED | `app/video/` (22 modules); `tests/video/test_directors.py` (24) | deterministic; drive `creative_plan` in `media_nodes.scene_plan` |
| VS-STORY-014 | Story beats (HOOK…CTA) affect production | IMPLEMENTED+TESTED | `app/video/story.py`; used in `creative_plan` + creative QA | — |
| VS-RETEN-015 | Retention checkpoints / boredom / visual refresh / info density → decisions | IMPLEMENTED+TESTED | `app/video/retention.py`, Creative QA V2; `tests/video/test_engines_v2.py` | retention *curve* needs platform analytics (labelled) |
| VS-CUT-016 | Cut Engine V2, shot duration variance, cut reason | IMPLEMENTED+TESTED | `app/video/cuts.py`; `test_engines_v2.py::test_cut_engine_*` | — |
| VS-REPAIR-017 | Smart Rerender — single scene only | IMPLEMENTED+TESTED | `app/video/rerender.py`; `test_engines_v2.py::test_rerender_*`, `tests/media/test_integration.py::test_scene_regeneration_touches_only_one_scene` | — |
| VS-TQA-018 | Technical QA: duration/res/fps/audio/subtitle/timeline + repair plan + quality 0–100 | IMPLEMENTED+TESTED | `app/video/technical_qa.py`; `test_engines_v2.py::test_quality_score_100_and_repair_plan` | — |
| VS-VMAF-019 | VMAF perceptual score | DESIGN_ONLY (optional adapter) | `app/video/adapters/` seam; not installed | correctly OPTIONAL / NOT_AVAILABLE, not PASS |
| P1B-ALIGN-020 | Forced alignment (WhisperX) | DESIGN_ONLY (optional) + estimator IMPLEMENTED | `app/media/word_timing.py` — `WhisperXAlignmentProvider` scaffold + working `EstimatorAlignmentProvider` fallback | real alignment NEEDS the model |

## PART C — Publishing (Phase 2)

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| P2-CAP-021 | 10-platform capability registry (SUPPORTED/AUTH_REQUIRED/APP_REVIEW/ACCOUNT_TYPE/LIMITED/MANUAL_ONLY/NOT_SUPPORTED) | IMPLEMENTED+TESTED | `app/publishing/capabilities.json` + `capabilities.py`; `tests/publishing/` | policy shapes verified; live platform terms NEEDS_PRODUCTION_ENVIRONMENT |
| P2-JOB-022 | PublishJob: idempotency, retry, scheduler, reconcile, DLQ | IMPLEMENTED+TESTED | `app/publishing/engine.py`, `service.py`, `reconcile.py`, `ops/dlq.py`; `tests/publishing/` (31), `tests/ops/` | — |
| P2-GATE-023 | Publisher final gate (governance + platform-selection, fail-closed) | IMPLEMENTED+TESTED | `engine.run_publish_job`; `tests/governance/test_e2e.py`, `tests/intel/test_platform_selection.py` | — |
| P2-ADAPT-024 | Real platform adapters (publish/analytics) | IMPLEMENTED+MOCK_VERIFIED | `app/publishing/publishers.py` + `mock_platform.py` | real OAuth + API = NEEDS_CREDENTIALS |
| P2-SCHED-025 | DB scheduler / scheduled publish | IMPLEMENTED+TESTED | `tasks.publish_scheduler_tick`, `schedule_job`; publishing tests | wall-clock cron = NEEDS_PRODUCTION_ENVIRONMENT |

## PART D — Analytics / Revenue / Learning (Phase 3)

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| P3-AN-026 | Capability-gated metrics; unknown ⇒ null (never 0) | IMPLEMENTED+MOCK_VERIFIED | `app/analytics/`; `AnalyticsSnapshot` nullable; grep confirms no `or 0`; `tests/analytics/` (16) | real API data = NEEDS_CREDENTIALS |
| P3-REV-027 | Revenue: actual vs estimated kept separate, never summed | IMPLEMENTED+TESTED | `RevenueEntry.is_estimate`; `monetization.profit_center` (D76); mb tests | real ad revenue = NEEDS_CREDENTIALS |
| P3-LEARN-028 | Evidence-based learning + false-learning guard + memory + experiments | IMPLEMENTED+TESTED | `app/learning/` (engine/memory/experiment/recipe); analytics tests | — |
| P3-PROMOTE-029 | Promotion recommendation (advisory) | IMPLEMENTED+TESTED | `learning/engine.py`; `learning/reports.py` | — |

## PART E — Trend / Autopilot (Phase 4)

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| P4-TREND-030 | 10 trend providers + two-stage opportunity scorer (17 dims, explainable) | IMPLEMENTED+MOCK_VERIFIED | `app/trends/`, `app/autopilot/signals.py`, `scoring.py`; `tests/autopilot/` (26) | real sources = NEEDS_CREDENTIALS |
| P4-AUTO-031 | Autopilot: topic select → produce → budget gate → platform select → governance gate → schedule; pause/emergency-stop; HARD RULES AI-immutable | IMPLEMENTED+TESTED | `app/autopilot/controller.py`, `bridge.py`, `emergency.py`; autopilot e2e | full-auto tests run DRY_RUN (Phase 2 gates real publish) |
| P4-SCHED-032 | Autopilot → real scheduler wiring | IMPLEMENTED+TESTED | `bridge.produce_from_context` → `create_jobs_for_campaign` + `schedule_job`; beat tasks | — |

## PART F — Production / Ops (Phase 5)

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| P5-INFRA-033 | Docker, compose (prod profile), queue split, health, resource limits | IMPLEMENTED + LOCAL_VERIFIED | `backend/Dockerfile`, `docker-compose.prod.yml`; `docker compose config` OK | live server = NEEDS_PRODUCTION_ENVIRONMENT |
| P5-BACKUP-034 | backup → verify → restore round-trip | IMPLEMENTED + LOCAL_VERIFIED | `app/ops/backup.py`; `tests/ops/test_backup_restore.py` (real pg_dump/restore into `acf_restore_test`) | off-site/S3, WAL/PITR = NEEDS_PRODUCTION_ENVIRONMENT |
| P5-OPS-035 | DLQ, leases, worker registry, rate-limit, redaction, SSRF, circuit breaker, cost-anomaly, alerts | IMPLEMENTED+TESTED | `app/ops/*`; `tests/ops/` (44) | external alert delivery = NEEDS_PRODUCTION_ENVIRONMENT |
| P5-SEC-036 | Secret scan, env validation (fail-closed in prod), upload security | IMPLEMENTED+TESTED | `scripts/security/scan_secrets.py` (runs clean incl. `.env.example`), `ops/env.py` | real TLS/domain = NEEDS_PRODUCTION_ENVIRONMENT |

## PART G — Multi-brand (Phase 6)

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| P6-AUTH-037 | Auth (stdlib pbkdf2 + HMAC key) + RBAC, backend 403 | IMPLEMENTED+TESTED | `app/auth/`; `tests/mb/test_auth_rbac.py::test_viewer_cannot_write_editor_can`, `::test_admin_endpoints_require_system_admin` | login UI + session cookies = follow-up |
| P6-ISO-038 | Workspace / Brand / Channel / PlatformAccount tenant scoping | IMPLEMENTED+TESTED | `app/mb/scope.py`; `tests/mb/test_isolation.py` (42 total in `tests/mb`) | — |
| P6-CRED-039 | Credential-scope isolation (Brand A token ≠ Brand B) | IMPLEMENTED+TESTED | `token_manager.assert_credential_scope` (D74); mb tests | — |
| P6-BUDGET-040 | Hierarchical hard budget, transactional reservation, race-safe | IMPLEMENTED+TESTED | `app/mb/budget.py` (`SELECT … FOR UPDATE`); `tests/mb/test_budget.py::test_concurrent_reservations_cannot_exceed_hard_limit` | — |
| P6-CHAN-041 | Channel & Portfolio managers — deterministic, advisory-only, no auto-delete | IMPLEMENTED+TESTED | `channel_manager.py`, `portfolio.py` (D75); mb tests | reposition LLM = DESIGN_ONLY |
| P6-SCHED-042 | Cross-channel scheduler / capacity planner | IMPLEMENTED+TESTED | `app/autopilot/capacity.py` (per-channel slots + budget headroom); Autopilot controller caps its run by `portfolio_capacity`; `GET /api/publishing/calendar/capacity`; `tests/autopilot/test_capacity.py` (5) | AUDIT-P6-001 RESOLVED (D95). Planner *UI* widget not built (LOW) |

## PART H — Governance (Phase 7)

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| P7-ENGINE-043 | Deterministic governance gate (no LLM verdict) → ALLOW/…/BLOCK | IMPLEMENTED+TESTED | `app/governance/engine.py`, `decision.py`; `tests/governance/` (46) | — |
| P7-RIGHTS-044 | Rights ledger, evidence, lineage, licence expiry, attribution, final manifest; UNKNOWN_RIGHTS blocked from auto-publish | IMPLEMENTED+TESTED | `governance/rights.py`, `manifest.py`; `test_e2e.py::test_publisher_cannot_publish_unknown_rights` | — |
| P7-DISC-045 | AI disclosure set at generation, carried to PublishJob, never stripped | IMPLEMENTED+TESTED | `governance/disclosure.py` (`assert_not_stripped`); `PlatformContent.payload.disclosure_meta` + `PublishJob.disclosure_meta` (ORM-mapped); governance tests | — |
| P7-ORIG-046 | Originality: text/script/image(pHash)/video-structure/transformation/cross-brand + vs learned references → production gate | IMPLEMENTED+TESTED | `governance/originality.py`, `intel/reference_guard.py`; `tests/governance/`, `tests/intel/test_governance_integration.py` | image/video CV is aHash/dHash + structure (heavy CV = OPTIONAL) |
| P7-VOICE-047 | Voice-clone consent-unknown → BLOCK (hard) | IMPLEMENTED+TESTED | `governance/identity.voice_clone_guard`; `test_gate.py::test_voice_clone_without_consent_blocks` | — |
| P7-POLICY-048 | Platform policy registry + verification | IMPLEMENTED+TESTED (fixtures + human-in-the-loop verify) | `governance/policy.py` (fixtures) + `governance/policy_verify.py` (review queue + attested `record_verification` + `GovernanceEvent`); `GET/POST /api/policy/verif*`; `tests/governance/test_policy_verify.py` (6) | AUDIT-P7-001 RESOLVED (D95). Live policy *fetch* stays NEEDS_PRODUCTION_ENVIRONMENT / LEGAL_REVIEW_REQUIRED |
| P7-BYPASS-049 | Hard BLOCK not bypassable by Publisher/Autopilot | IMPLEMENTED+TESTED | `_HARD_BLOCK_CODES`, `apply_human_override` refuses; both gates fail-safe | — |

## PART I — URL Learning / Dataset (Intelligence Upgrade)

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| IU-URL-050 | URL validate + SSRF (per-redirect) + classify + fetch + clean + chunk | IMPLEMENTED+TESTED | `app/intel/url_security.py`, `fetch.py`, `extract.py`; `tests/intel/test_url_learning.py` (30) | JS-render adapter (browser) OFF by default (D67) |
| IU-INJ-051 | Prompt-injection detector — untrusted content, never executed | IMPLEMENTED+TESTED | `app/intel/injection.py`; `test_url_learning.py::test_injection_detector_flags_and_sanitizes`, `test_intel_api.py::test_ssrf_blocked_url_is_reported_not_fetched` | — |
| IU-SSRF-052 | localhost/127.*/private/metadata/file:/gopher:/redis/postgres blocked for user URLs; internal Ollama endpoint trusted separately | IMPLEMENTED+TESTED | `url_security._literal_ssrf_check`; `LOCAL_AI.md` §78; url-learning tests | — |
| IU-REF-053 | Reference library: source/chunks/analysis/scope/collection, tenant-scoped, rights separated | IMPLEMENTED+TESTED | `models_learn.py`; `tests/intel/test_isolation_and_rights.py::test_reference_use_does_not_create_media_rights` | — |
| IU-DS-054 | DatasetRecord + quality/trust/relevance/freshness/originality/weight + dedup | IMPLEMENTED+TESTED | `app/intel/dataset.py`, `quality.py`; `tests/intel/test_dataset.py` (6) | — |
| IU-CUR-055 | DataCurator: duplicate/spam/noise/stale/wrong-lang/rights → weight + deactivate | IMPLEMENTED+TESTED | `dataset.curate`; `test_dataset.py::test_curator_deactivates_rights_problem_records` | — |
| IU-VIDLEARN-056 | Video reference deep analysis (from supplied structured profile; UNKNOWN otherwise) | IMPLEMENTED+TESTED | `app/intel/analyzers.py`; `tests/intel/test_distillation.py::test_video_distillation_from_many_profiles` | real frame CV = OPTIONAL adapter |

## PART J — LEARN_ONLY / Prompt Distillation

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| IU-LO-057 | LEARN_ONLY → Campaign/AI-image/AI-video/TTS/render/PublishJob/SNS = 0; references/datasets/profiles/blueprints/skills > 0 | IMPLEMENTED+TESTED | `app/intel/modes.py` guard + `create_jobs_for_campaign`/`run_publish_job` short-circuit; `tests/intel/test_learn_only.py` (5) | — |
| IU-DIST-058 | Prompt distillation — reverse-inferred guidance, never "recovered the creator's prompt", never verbatim text | IMPLEMENTED+TESTED | `app/intel/distillation.py`; `test_distillation.py::test_copyright_source_text_not_copied_into_blueprint` | — |
| IU-BP-059 | PromptBlueprint schema (agent/purpose/instructions/constraints/±patterns/platform/ct/cluster/quality/confidence/sample/status/version/evidence) | IMPLEMENTED+TESTED | `models_learn.PromptBlueprint` + `PromptBlueprintEvidence`; distillation tests | — |
| IU-PROMO-060 | 1 reference cannot reach PROMOTED; status state machine; AUTO_PROMOTE=false | IMPLEMENTED+TESTED | `distillation.advance_status` + `_TRANSITIONS`; `test_distillation.py::test_single_reference_cannot_pass_experimental`, `::test_promotion_state_machine_and_rollback` | — |
| IU-COMP-061 | PromptComposer merges Base+Brand+Channel+Memory+Skills+Blueprints under token budget | IMPLEMENTED+TESTED (on the agent path) | `model_gateway._compose_system()` runs `composer.compose(...)` before routing; `tests/agents/test_prompt_composer_wiring.py` (11) + `tests/intel/test_composer.py` (5) | AUDIT-P8-006 RESOLVED (D95) |
| IU-SKILL-062 | LearnedSkillNote used by composer retrieval in production | IMPLEMENTED+TESTED | `composer.relevant_skills` (agent-alias + platform + brand + disable-switch filtered) called from `model_gateway`; lineage in `ModelRoutingEvent.prompt_lineage` | AUDIT-P8-006 RESOLVED (D95) |
| IU-RECIPE-063 | CreativeRecipe — combine features from several references (not a creator clone) | IMPLEMENTED+TESTED | `skills.compose_creative_recipe`; `models_learn.CreativeRecipe` | recipe → production application is DESIGN_ONLY |

## PART K — SNS Selection

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| IU-SEL-064 | 3-state DISABLED / GENERATE_ONLY / GENERATE_AND_PUBLISH | IMPLEMENTED+TESTED | `app/intel/platform_selection.py`; `tests/intel/test_platform_selection.py` (8) | — |
| IU-OFF-065 | Platform OFF ⇒ adaptation/media/job/API = 0 (service + worker + publisher) | IMPLEMENTED+TESTED | `set_selection` sets `Campaign.platforms`; `create_jobs_for_campaign` filters; `run_publish_job` re-checks; `test_platform_selection.py::test_generation_skip_no_jobs_for_off_platform` | — |
| IU-RACE-066 | Queue ON→OFF→worker ⇒ remote API 0 | IMPLEMENTED+TESTED | `run_publish_job` re-reads selection; `::test_publisher_gate_blocks_deselected_platform_race` | — |
| IU-REEN-067 | Re-enable reuses assets, 0 dup job | IMPLEMENTED+TESTED | idempotency key; `::test_reenable_reuses_assets_no_duplicate_job` | — |
| IU-OVR-068 | Autopilot cannot re-enable user-OFF platform | IMPLEMENTED+TESTED | `platform_selection.autopilot_may_enable` + `platform_selection_locked`; `::test_autopilot_cannot_reenable_user_disabled_platform` | — |

## PART L — Content Library (Phase 8)

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| P8-LIB-069 | Read model over ALL existing content (not just post-Phase-8) | IMPLEMENTED+TESTED | `app/library/service.py` walks every `Campaign`; `tests/library/test_content_library.py::test_existing_content_is_discovered` | — |
| P8-LEGACY-070 | Legacy (no workspace + no execution_mode) renders, no crash, governance NOT_APPLICABLE | IMPLEMENTED+TESTED | `_is_legacy`; `::test_legacy_detail_does_not_crash_and_marks_not_applicable` | — |
| P8-PREVIEW-071 | Real MP4 streamed to browser | IMPLEMENTED+TESTED | `GET /api/library/{id}/media/video` (`FileResponse`); `tests/library/test_library_api.py::test_library_video_stream` | — |
| P8-DETAIL-072 | 12 tabs, each DB/API-backed | IMPLEMENTED+TESTED | `content_detail`; `/api/library/{id}/{tab}`; library API tests | NL-edit backend + `POST /api/library/{id}/edit-plan` done (AUDIT-P8-002); scene-editor *panel* UI = LOW |
| P8-HIST-073 | Version history (script/asset/governance) | IMPLEMENTED+TESTED | `_history`; `::test_legacy_detail_...` asserts history present | prompt/scene/platform-selection history via related tabs only |
| P8-ADD-074 | Add platform later → only new platform generated, 0 regen; 409 if selected | IMPLEMENTED+TESTED | `add_platform_to_campaign`; `::test_add_platform_later_only_adds_new`, `test_library_api.py::test_add_platform_endpoint` | pipeline run for the new platform is a manual/separate call (documented) |
| P8-DEMO-075 | Sample renders flagged `is_demo`, not shown as production | IMPLEMENTED+TESTED | `_is_demo`; `::test_demo_video_flagged_not_production` | — |
| P8-SEARCH-076 | Global search (campaign/platform-content/channel/brand/reference/publication) | IMPLEMENTED+TESTED | `app/library/search.py::global_search` + `GET /api/search`; `tests/library/test_global_search.py` (5) | AUDIT-P8-003 RESOLVED (D95) |

## PART M — Local AI / Model Router / Cost (Phase 8)

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| P8-OLLAMA-077 | Ollama provider: health/list/generate/timeout/error-normalization/structured JSON | IMPLEMENTED + LOCAL_VERIFIED | `app/providers/ollama_llm.py` (stdlib HTTP, no `ollama` pkg); `tests/ai_router/test_ollama.py` (4); LIVE probe `gemma3:4b` → `{"label":"NEWS"}` 2.3 s | — |
| P8-OLLAMA-OPT-078 | Ollama down ⇒ app boots, no crash; HTTP 200 `NOT_RUNNING` | IMPLEMENTED+TESTED | `health()` never raises; `test_ollama.py::test_health_never_raises_when_down`, `test_ai_api.py::test_local_ai_status_never_500` | — |
| P8-LOCALONLY-079 | LOCAL_ONLY ⇒ 0 cloud calls | IMPLEMENTED+TESTED | `router._candidates` drops cloud when `local_only`; `execute._provider_for` refuses cloud; `test_execute.py::test_local_only_never_calls_cloud_even_on_local_failure` | — |
| P8-FALLBACK-080 | Cloud fallback only when ALLOW_CLOUD_FALLBACK=true | IMPLEMENTED+TESTED | `test_execute.py::test_local_failure_falls_back_when_cloud_allowed` | — |
| P8-REG-081 | Model Registry: provider/model/local-cloud/health/caps/context/vision/latency/quality/pricing | IMPLEMENTED+TESTED | `app/ai_router/registry.py`; `test_router.py`, `test_ai_api.py::test_models_endpoint_*` | — |
| P8-ROUTE-082 | Router selects by task fit (deterministic/local_light/standard/premium), not price only | IMPLEMENTED+TESTED (subsystem **+ agent path**) | `app/ai_router/router.py` + `app/agents/model_gateway.py`; `tests/ai_router/test_router.py` (10) + `tests/agents/test_model_gateway.py` (15) | AUDIT-P8-001 RESOLVED — `_run_llm`/`_llm_json` route through the gateway; full-campaign telemetry proves standard+premium routing |
| P8-AGENTPOL-083 | Per-agent tier policy (Research/Fact/Hook/Script/Curator/…) | IMPLEMENTED+TESTED (on the agent path) | `router.AGENT_TIER` + `model_gateway._TASK_MAP`; `test_model_gateway.py::test_agent_policy_sets_routing_tier` (research/fact/platform_adapt/scene_plan→standard; strategy/hook/script→premium) | — |
| P8-ESC-084 | Escalation on schema-invalid / low-confidence; bounded chain | IMPLEMENTED+TESTED | `execute.run_routed`; `test_execute.py::test_schema_invalid_escalates_to_next_engine` | — |
| P8-BENCH-085 | Model benchmark on our task set (schema/accuracy/latency/cost/failure) | IMPLEMENTED+TESTED | `app/ai_router/benchmark.py`; `test_ai_api.py::test_benchmark_runs_on_mock_and_records_performance` | real-model benchmark = MOCK_VERIFIED unless run against Ollama/cloud |
| P8-TELE-086 | Routing telemetry + ModelPerformance memory + auto-tune | IMPLEMENTED+TESTED | `ai_router/telemetry.py` + `ModelRouter._apply_performance` (STRONG↑/WEAK↓, min-sample guarded); `tests/ai_router/test_telemetry.py` (3) + `test_autotune.py` (3) | AUDIT-P8-005 RESOLVED (D95) |
| P8-COST-087 | Cost estimator: LLM/Search/Image/Video/TTS/Stock/Storage with KNOWN/ESTIMATED/UNKNOWN; no fake prices | IMPLEMENTED+TESTED | `app/ai_router/cost.py` (genuinely calls the router for LLM lines); `tests/ai_router/test_cost.py` (6) | media always UNKNOWN (MOCK); cloud prices ESTIMATED until operator-verified |
| P8-COST-PLAT-088 | Platform OFF ⇒ 0 platform cost; shared master counted once; recompute on change | IMPLEMENTED+TESTED | `cost.estimate_campaign_cost`; `test_cost.py::test_disabled_platform_adds_no_platform_specific_cost`, `::test_shared_master_media_counted_once` | — |
| P8-BUDGET-089 | Budget hard gate at execution (not just preview) | IMPLEMENTED+TESTED | pre-existing `check_budget` (Phase 1) + `mb/budget.reserve` (Phase 6) still enforced; `tests/test_budget_guard.py`, `tests/mb/test_budget.py` | Phase-8 cost *preview* does not itself gate — enforcement is the existing budget guard (acceptable) |

## PART N — Phase 8 UX

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| P8-WIZ-090 | Setup Wizard 8 steps + server persistence | IMPLEMENTED+TESTED | `finishSetup` POSTs `/api/workspaces` + `/api/brands` (now commit); `tests/mb/test_setup_wizard_persistence.py` (2); `tsc` clean | AUDIT-P8-004 RESOLVED (D95). Step progress still `localStorage` (by design) |
| P8-QC-091 | Quick Create → backend compose | IMPLEMENTED+TESTED | `/create` → `POST /api/campaigns/compose`; `tests/test_phase8_e2e.py::test_beginner_create_lands_in_content_library` | — |
| P8-PROG-092 | Progress reflects real backend job state | IMPLEMENTED (reused) | Phase 1-A/1-B `agent_runs` + `current_step` + `media_tasks`; existing campaign detail page | Phase 8 didn't add a new progress widget — uses existing `/campaigns/[id]` |
| P8-PRC-093 | Pause / Resume / Cancel wired to worker/job | IMPLEMENTED (reused) + TESTED | checkpointer + `run_pipeline(resume=True)` + autopilot emergency pause; `tests/test_checkpoint_resume.py`, `tests/media/test_failure_resume.py` | — |
| P8-NLE-094 | Natural-language edit → structured EditRequest | IMPLEMENTED+TESTED (backend) | `app/edit/nl_to_request.py` (deterministic KR/EN phrase table); `tests/edit/test_nl_to_request.py` (5) | AUDIT-P8-002 RESOLVED (D95); panel UI = LOW |
| P8-IMPACT-095 | Impact analyzer — rerun only affected pipeline | IMPLEMENTED+TESTED | `edit.nl_to_request.impact_of` wraps `plan_rerender` into a human "re-runs X" preview; `POST /api/library/{id}/edit-plan` | AUDIT-P8-002 RESOLVED (D95) |
| P8-REVUX-096 | Review Center reads governance queue | IMPLEMENTED (reused) | `/governance` reads `GET /api/governance/review` + `/cases`; `tests/governance/` | Phase 8 reuses the Phase 7 page (acceptable) |
| P8-SAFEFIX-097 | Safe-fix buttons → real services | IMPLEMENTED+TESTED (backend) | `POST /api/governance/repair` → `governance/repair.apply_fix` (music/B-roll replace, disclosure/attribution); `tests/governance/test_gate.py::test_ai_disclosure_required_then_satisfied` | frontend `/governance` exposes repair; per-button E2E not separately tested |
| P8-CAL-098 | Calendar ↔ scheduled publications + capacity | IMPLEMENTED+TESTED | `GET /api/publishing/calendar` + `/calendar/capacity` (`portfolio_capacity`); publishing + `tests/autopilot/test_capacity.py` | capacity planner RESOLVED (P6-SCHED-042) |
| P8-REPORTS-099 | Daily / Weekly / Monthly reports | IMPLEMENTED (reused) | `app/learning/reports.py`, `app/autopilot/reports.py`; `/api/analytics` report routes | no new Phase-8 report UI page |
| P8-NOTIF-100 | Notifications from real events | IMPLEMENTED (reused) | `app/ops/alerts.py` (`raise_alert`, dedup, `DashboardNotifier`); ops tests | external delivery (email/Slack) = NEEDS_PRODUCTION_ENVIRONMENT |
| P8-A11Y-101 | Responsive + accessibility (status by text+colour, labels, semantic controls) | IMPLEMENTED | Tailwind responsive classes; status text beside colour dots in `/system`, `/calendar`, `/library`; `tsc` + `next build` clean | no automated a11y test (project has no JS test runner) |
| P8-TEMPLATE-102 | Template system CRUD | NOT_IMPLEMENTED (this scope) | `platform_presets` covers SNS-selection presets; content templates not requested for Phase 8 | LOW — not a Phase-8 requirement |

## PART O — Cross-cutting

| ID | Feature | Status | Evidence | Gap |
|---|---|---|---|---|
| X-RT-110 | ORM ↔ migration alignment | IMPLEMENTED (verified) | 97 ORM tables, 0 column mismatches, single head, no destructive DDL | — |
| X-WR-111 | write/read path for governance / disclosure / platform selection / prompt lineage / learning / cost / model routing / content history | IMPLEMENTED+TESTED | each has model + writer + reader + test (see rows above); governance & disclosure ORM-mapped on `PlatformContent`/`PublishJob` this session | — |
| X-DEP-112 | Dependency discipline | IMPLEMENTED (verified) | 0 new deps in Phases 6/7/8/intel; no `ollama`/`playwright`; unused-dep scan: none | — |
| X-SEC-113 | Secrets / SSRF / tenant leak / RBAC / publisher gate / governance bypass / external-content execution / GitHub-learning shell | IMPLEMENTED+TESTED | `scan_secrets` clean; `tests/ops` security; `tests/mb` RBAC/isolation; `tests/intel` injection+SSRF; `tests/governance` bypass; `intel/analyzers.github_analysis` reads text only, no exec | — |
