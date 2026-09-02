# AGENT / SKILL INVENTORY

GitHub Best-of-Breed Audit — step 1. Every agent, engine, skill, provider and
service that **actually exists in `backend/app/`** (code, not docs), with its
current implementation and an honest strengths/weaknesses read.

Reviewed 2026-08-31 against the code at Phase 5 head. Companion:
`docs/BEST_SKILL_MATRIX.md` (GitHub comparison + decisions).

Legend — **LLM**: does the component call an LLM today? **Det-possible**: could
the whole thing be deterministic code with no quality loss?

---

## A. Orchestration / Runtime

### A1. Pipeline Graph (Master Orchestration — Phase 1-A)
- **type**: engine — `app/agents/graph.py`, `runner.py`, `state.py`
- **purpose**: run Topic → Research → FactCheck → (fix loop) → Strategy → Hook → Script → QA → Persist for one campaign.
- **current impl**: LangGraph `StateGraph` over a `TypedDict` state; fixed linear edges + one conditional edge (`fact_score_router`); Postgres checkpointer (thread_id = campaign_id) → durable resume; `recursion_limit=50`.
- **dependencies**: `langgraph==0.2.60`, `langgraph-checkpoint-postgres==2.0.9`.
- **LLM**: no (nodes call it). **Det-possible**: N/A (it's the harness).
- **strengths**: durable/resumable already; state is a single typed object; graph is trivial to read; no second runtime.
- **weaknesses**: hard-wired topology — no planner, no supervisor, no dynamic skip; `langgraph` pin is ~8 months stale (0.2.60; current line is 0.6.x) and misses `langgraph-supervisor`, `interrupt()` HITL, deferred nodes, durability modes; every node is mandatory (no SkillRouter).

### A2. Media Pipeline Graph (Phase 1-B)
- **type**: engine — `app/agents/media_graph.py`, `media_nodes.py`, `media_runner.py`, `media_state.py`
- **purpose**: Knowledge Pack → platform content → scenes → visual plan → media gen → render → thumbnail/images → QA → scene regen.
- **current impl**: second LangGraph graph, same checkpointer pattern; nodes are mostly deterministic with LLM only for scene/plan text.
- **LLM**: partial. **Det-possible**: mostly yes (already is).
- **strengths**: cost-aware, fallback-heavy, deterministic renderer; regen loop.
- **weaknesses**: same rigidity as A1; no concurrency across scenes (sequential render); no planner deciding *which* QA passes are needed.

### A3. Autopilot Controller (Phase 4)
- **type**: engine — `app/autopilot/controller.py` + 18 sibling modules
- **purpose**: OFF/SHADOW/SUGGEST_ONLY/SEMI_AUTO/FULL_AUTO loop: ingest trends → candidate pipeline → score → portfolio → (produce → recheck → publish) → watchdog.
- **current impl**: plain Python orchestration (not LangGraph); calls `run_pipeline` → `run_media_pipeline` → `create_jobs_for_campaign`; idempotent by `candidate_id`; HARD RULES enforced in code; Phase 5 backpressure + emergency-stop flags wired in.
- **LLM**: only via the sub-pipelines + topic extraction. **Det-possible**: mostly yes (scoring/portfolio already deterministic).
- **strengths**: clear staged flow; resumable by `resume_run_id`; risk matrix overrides run mode; sunk-cost rule.
- **weaknesses**: bespoke control flow with no checkpoint of its *own* (relies on child graphs + DB rows); no compensation/saga if produce succeeds but publish-scheduling fails mid-batch.

### A4. Celery task layer
- **type**: service — `app/celery_app.py`, `app/tasks.py`
- **purpose**: async execution + beat schedules (autopilot, analytics, ops heartbeat/backup/stuck-scan).
- **current impl**: Celery 5.4 + Redis; queue-split (`celery,image,video,audio,render,publish,analytics,autopilot`); Phase 5 signal handlers (worker register/heartbeat/lease release).
- **LLM**: no. **Det-possible**: yes.
- **strengths**: mature; queue isolation; Phase 5 heartbeat + `JobLease` duplicate guard.
- **weaknesses**: Celery gives at-least-once + our own idempotency; no journal/replay (that's LangGraph's job); ret/backoff config is scattered.

---

## B. Research & Knowledge

> **Continuation pass (2026-08-31 part 2) upgraded B1, B5, C2 and F6** — see the
> ⤴ notes under each and `docs/DECISIONS.md` D68–D69. New deterministic helper
> modules: `app/agents/research.py`, `app/agents/factcheck.py`, `app/agents/hooks.py`.

### B1. Research Agent
- **type**: agent — `app/agents/nodes.py::_do_research` (+ `app/agents/research.py`)
- ⤴ **upgraded**: first-pass **query decomposition** (`expand_queries` → 3 complementary sub-queries), **merge_and_rank** (domain authority × topical match × freshness) with a **domain-diversity cap**, **contradiction discovery** (`find_contradictions` → `kp["contradictions"]`), **source_diversity** + **coverage_score** on the KP as an extra stopping signal. Fix pass keeps its 1-query angle rotation.
- **purpose**: gather sources for a topic, extract candidate facts + audience + stats + examples + counter-args + keywords + risk flags.
- **current impl**: **one** `search.search(query, max_results=6)` call; on the fix pass the query is a fixed string append (`"{topic} 통계 최신 근거 사례"`); then **one** LLM call turns snippets into a structured Knowledge Pack. Retry via `call_with_retry`. `InsufficientResearchError` if < 2 results.
- **dependencies**: `SearchProvider` (mock / Tavily), `LLMProvider`.
- **LLM**: yes (1 call/pass). **Det-possible**: no (synthesis needs judgment) — but query planning could be deterministic.
- **strengths**: cheap, bounded, deterministic in mock, fully logged/costed; fix loop exists.
- **weaknesses**: **no query decomposition** (single query per pass); no parallel sub-queries; no source-diversity / primary-source preference; no iterative "do I have enough?" stopping criterion beyond the fact-score gate; freshness only via the provider's `published_at`; no contradiction discovery in the research step itself; max 2 fix passes total.

### B2. Deep Research
- **status**: **does not exist as a distinct component.** B1 is the entire research capability. No multi-hop, no research budget object, no research tree.

### B3. Web Search Provider
- **type**: provider — `app/providers/mock_search.py`, `tavily_search.py`, `registry.py`
- **current impl**: `SearchProvider` Protocol; deterministic mock catalogue; real `TavilySearchProvider` (`tavily-python==0.5.0`). `search_cost()` fixed per provider.
- **LLM**: no. **Det-possible**: yes (mock is).
- **strengths**: clean adapter; offline default; cost tracked.
- **weaknesses**: single vendor for "real"; no SearXNG / Brave / Exa / Firecrawl option; no page-fetch/extract step (snippets only — no full-text read); Tavily pin is old.

### B4. Source Ranking
- **status**: **minimal.** Sources are stored in provider order; the LLM implicitly weighs them. No explicit domain-authority, recency, or diversity ranking; no dedup of near-identical sources.

### B5. Fact Checker
- **type**: agent — `app/agents/nodes.py::fact_check_node` (+ `app/agents/factcheck.py`)
- ⤴ **upgraded**: **atomic claim extraction** (`atomic_claims` — splits a compound claim on clause boundaries; no-op on a claim with none, incl. every mock fact), **check-worthiness** filter (skip pure opinion), **cross-source agreement count**, **temporal-marker** extraction, **confidence re-blend** (`blend_confidence` — no sources ⇒ capped 0.3; +agreement; numeric-claim-without-temporal ⇒ −0.05), lone-source `VERIFIED → PARTIALLY_VERIFIED`.
- **purpose**: label each candidate fact VERIFIED / PARTIALLY_VERIFIED / UNVERIFIED / CONTRADICTED with confidence + source_ids + reason; compute `fact_score = usable/total`.
- **current impl**: **one** LLM call over `{candidate_facts, sources[snippet]}`; result persisted; score gates the research-fix loop (`fact_score_threshold`, default 0.6).
- **LLM**: yes (1 call). **Det-possible**: no (entailment judgment).
- **strengths**: structured output, per-fact evidence + reason, drives a real control-flow gate; unverified facts are tracked and blocked downstream (`script_qa` fails on `used_unverified_fact`).
- **weaknesses**: **no atomic claim splitting** (checks the facts the research step happened to emit, at whatever granularity); no cross-source agreement count; no per-source reliability weight; no temporal check ("true as of when"); works from **snippets, not fetched source text**; single pass (no re-retrieval for a shaky claim).

### B6. Knowledge Pack / RAG
- **type**: data structure — built in `_do_research`, stored on `Campaign.knowledge_pack`
- **current impl**: a dict (`verified_facts, statistics, examples, sources, counter_arguments, interesting_points, visual_opportunities, keywords, risk_flags`). No vector store, no chunking, no retrieval — it's a single JSON blob passed forward in state.
- **LLM**: no (consumed by later prompts). **Det-possible**: yes.
- **strengths**: simple, sufficient for a single short-form piece; single source of truth in state + DB.
- **weaknesses**: not reusable across campaigns; no entity/relation structure; no "retrieve the 3 facts relevant to this scene" — every downstream prompt gets the whole pack.

---

## C. Content & Writing

### C1. Content Strategist
- **type**: agent — `strategy_node`
- **current impl**: one LLM call → `{angle, key_message, tone, target_emotion, talking_points}`; injects Phase 3 strategy memories as **advisory text** (`strategy_memory_context`), never as facts; wrapped so a learning failure never blocks strategy.
- **LLM**: yes. **Det-possible**: no.
- **strengths**: memory injection is bounded + advisory; objective-aware.
- **weaknesses**: no explicit story-architecture model (no beat sheet / narrative arc structure); no multiple-strategy generation + selection.

### C2. Hook Agent
- **type**: agent — `hook_node` (+ `app/agents/hooks.py`)
- ⤴ **upgraded**: **diversity_filter** (drop near-dupe hooks, `min_keep=3` floor), **recent-hook similarity penalty** (vs other campaigns' recent hooks), **platform-aware re-rank** (`_PLATFORM_TILT`), **factual-exaggeration guard** (`exaggeration_flags` — absolute/superlative claims + numbers not traceable to a verified fact; time-span numbers like "3년간" excluded from the stat check). Hooks persisted ranked by `adjusted_score`.
- **current impl**: one LLM call → N hooks each `{text, style, score}`; `max(score)` chosen; all stored ranked.
- **LLM**: yes. **Det-possible**: no (creative).
- **strengths**: generates a set + self-scores + keeps them for learning (`HOOK` memory dimension).
- **weaknesses**: the score is the model's own single-shot number — no retention-pattern rubric, no platform-specific hook templates, no A/B of hooks against learned `hook_type` performance at generation time.

### C3. Script Agent + Natural Writing
- **type**: agent + engine — `script_node`, `app/naturalness/writing.py`
- **current impl**: draft LLM call → CTA appended (`pick_cta`, deterministic rotating) → **Natural Writing Pass**: if a real LLM, one rewrite call with a "human editor" system prompt; else a **deterministic** pass (`_deterministic`): strip banned openers/clichés, de-dupe sentence-initial connectives, one rhythm-variation pass (split longest / merge two shortest). Then a **fact-preservation check** (`_facts_preserved`: verified strings kept, unusable strings absent, **number set equality**) — reverts to draft on failure.
- **LLM**: yes (2 calls with real provider; 1 in mock). **Det-possible**: partly (the natural pass has a real deterministic mode).
- **strengths**: fact/number preservation is enforced structurally, not by prompt; deterministic fallback; voice profile fed in.
- **weaknesses**: deterministic rhythm pass is crude (one split + one merge, Korean-only heuristics); no retention-writing structure; no anti-repetition across the *whole* script beyond connectives; `_facts_preserved` is exact-substring (paraphrase of a kept fact = false failure → silent revert).

### C4. Script QA
- **type**: agent — `script_qa_node`
- **current impl**: one LLM call → `{passed, issues, used_unverified_fact}`; combined with a deterministic AI-slop threshold check; `passed` requires all three.
- **LLM**: yes. **Det-possible**: partly.
- **strengths**: hard gate on unverified-fact usage + slop score; issues surfaced to `Campaign.error_message`.
- **weaknesses**: no check for claim drift vs the *strategy* key_message beyond the prompt; no readability/grade-level metric; LLM pass/fail is single-shot.

### C5. AI-Slop / Naturalness Score
- **type**: skill — `app/naturalness/slop.py::score_ai_slop`
- **current impl**: 8 deterministic sub-scores (uniform sentence length via coefficient of variation, repeated connectives, importance-marker spam, clichés, template opener, rigid triads, filler intensifiers, uniform paragraph starts) → 0–100, plus `burstiness` (stdev of sentence word counts) + human-readable `tells`.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: fully deterministic, explainable, cheap, Korean+English tells, tuned threshold (≤20); **explicitly not an AI-detector-evasion score**.
- **weaknesses**: bag-of-phrases; no semantic repetition detection (same idea twice in different words); no discourse-coherence signal; thresholds are hand-set, never calibrated against Phase 3 performance.

### C6. Voice Profile
- **type**: skill — `app/naturalness/voice.py`
- **current impl**: `VoiceProfile` dataclass (formality/humor/directness/energy/question_freq/… + sentence-length distribution + favorite/forbidden expressions); loaded from `brands/<brand>/voice_profile.json`, else derived from `writing_samples/*.txt` via `analyze_samples` (sentence lengths, question ratio, crude formality proxy), else default.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: per-brand not generic; sample-derived; never copies sample sentences.
- **weaknesses**: `analyze_samples` is very shallow (3 numeric proxies); no lexical fingerprint, no n-gram style model, no tone classifier; not validated against output.

### C7. CTA Rotation
- **type**: skill — `app/naturalness/cta.py`
- **current impl**: fixed library of 6 CTA types × 1–2 variants; `pick_cta` = sha256(seed) mod, skipping last 3 used types.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: deterministic anti-repetition, seeded.
- **weaknesses**: tiny hand-written library; no performance feedback (which CTA type actually converts on which platform — Phase 3 has `cta_type` as a dimension but it doesn't feed back here).

---

## D. Platform Adaptation & Media Planning

### D1. Platform Registry
- **type**: reference — `app/platforms/registry.py`
- **current impl**: static capability table for ~13–14 platforms (aspect ratios, max duration, caption limits, hashtag norms).
- **LLM**: no. **Det-possible**: yes (is). **strengths**: single source of platform constraints. **weaknesses**: hand-maintained; drifts from real platform limits over time.

### D2. Scene Planner
- **type**: agent — `app/agents/media_nodes.py`
- **current impl**: LLM turns the script into scenes `{narration, source_ids, visual hint, duration target}` around `scene_target_seconds` (4.5s).
- **LLM**: yes. **Det-possible**: no (segmentation needs judgment).
- **weaknesses**: no beat/rhythm model for scene *durations* (fixed target); no re-planning if render cost blows the budget.

### D3. Visual Director
- **type**: skill — `app/media/visual_director.py`
- **current impl**: **fully deterministic** keyword rules: numbers+comparison → CHART (needs verified `source_ids`, else TEXT_CARD); short + emphasis → TEXT_CARD; real-scene words → STOCK_VIDEO; motion words → AI_VIDEO; else AI_IMAGE. Then budget/availability **downgrade cascade** (AI_VIDEO cap = `n * max_ai_video_ratio`; downgrades recorded with `downgraded_from`).
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: explainable, cost-capped, provenance on every downgrade, chart requires real sources.
- **weaknesses**: Korean keyword lists only; no semantic match of narration → visual concept (a scene about "layoffs" with no trigger word gets a generic AI_IMAGE); camera motion is just `i % 6` round-robin.

### D4. AI Image / Video / Stock / TTS / Music Providers
- **type**: providers — `app/providers/media/*`
- **current impl**: `MediaProvider` bases + deterministic mocks (`mock_image` draws a captioned gradient, `mock_tts` writes silence of the right length, `mock_stock` returns catalogue clips, `mock_music` a tone bed); `manager.py` + `cache.py` (asset cache) + `storage.py`; real adapters raise `NEEDS_CREDENTIAL`.
- **LLM**: no. **Det-possible**: yes (mocks are).
- **strengths**: every media type has a working offline path; cache keyed by content; `max_ai_video_ratio` gate.
- **weaknesses**: no real adapter implemented for *any* media type; `mock_stock` "semantic" search is keyword overlap; no CLIP / embedding match of narration → clip.

### D5. Image Motion Engine
- **type**: skill — `app/media/image_motion.py`
- **current impl**: 7 deterministic `zoompan` expressions (zoom/pan/Ken-Burns) built as FFmpeg filter strings; universal fallback so no scene is ever frozen.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: solves the "static image looks dead" problem with zero deps; argument-list FFmpeg (no shell).
- **weaknesses**: `zoompan` at 2× upscale is CPU-heavy and can shimmer; no motion direction chosen from image content (saliency); fixed 0.0009 zoom rate.

### D6. Word Timing / Alignment
- **type**: provider — `app/media/word_timing.py`
- **current impl**: `EstimatorAlignmentProvider` (default) — distributes real audio duration across tokens by a syllable/char weight + trailing-punctuation pause weight. `WhisperXAlignmentProvider` is **scaffolded but raises NotImplementedError**; `get_alignment_provider()` falls back to estimator if whisperx import fails.
- **LLM**: no. **Det-possible**: yes for the estimator; real alignment needs a model.
- **strengths**: honest ("proportional estimate", not fake forced alignment); deterministic; good enough for a mock TTS bed.
- **weaknesses**: **estimator is wrong for real speech** (ignores actual phoneme timing, pauses, emphasis); WhisperX path is a stub — the "optional real alignment" story is unfinished.

### D7. Subtitle / Caption Engine
- **type**: skill — `app/media/subtitles.py`
- **current impl**: Korean **phrase-unit line breaking** (break after particles/clause endings, ≥10 chars), `build_blocks` groups word timings onto phrase boundaries with a char budget, number/keyword **highlight** extraction; writers for SRT / ASS (styled, highlight color) / renderer JSON / **Pillow burn-in overlays** (libass-free path).
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: genuinely good Korean line-breaking; 4 output formats; deterministic; highlight logic; works without libass.
- **weaknesses**: no karaoke/word-pop timing animation (blocks only "pop" as a flag, no per-word reveal in the burn-in path); highlight cap of 3; no speaker/emphasis styling from prosody; `phrase_units` word-realignment is "best-effort" and can drift.

### D8. Caption Animation
- **status**: **flag only.** `SubtitleBlock.animation` carries `"pop"` but the Pillow overlay path renders a static plate. No kinetic/karaoke captions.

### D9. Automatic Video Editing / Scene Detection / Silence
- **type**: skills — `app/media/ffmpeg.py` (`detect_black`, `detect_silence`), renderer
- **current impl**: `detect_silence` (silencedetect) and `detect_black` (blackdetect) via FFmpeg stderr parsing; used in `media_qa`. **No cut-list editor** — the renderer concatenates planned scene clips; it does not trim dead air from real footage (there is no real footage in mock).
- **LLM**: no. **Det-possible**: yes.
- **strengths**: detectors exist and are used for QA; argument-list FFmpeg; `probe()` works without ffprobe.
- **weaknesses**: no auto-editor-style silence-removal cut list; no beat detection; no scene-boundary-aware cutting (PySceneDetect referenced in docs, not wired).

### D10. FFmpeg Renderer
- **type**: engine — `app/media/renderer.py`, `ffmpeg.py`
- **current impl**: deterministic assembly: per-scene motion clip → concat → mix voice + BGM (ducking) → burn subtitles (overlay PNGs) → `+faststart`. `run_ffmpeg` = argument list, `-loglevel error`, timeout, tail-only error. Edit Decision is data the model emits; rendering is always code.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: no shell injection surface; timeouts; deterministic; the "AI emits EDL, code renders" split is clean.
- **weaknesses**: sequential (no parallel scene encode); `veryfast`/software x264 only; re-encodes everything (no stream copy where possible); no NVENC/QSV path.

### D11. Thumbnail Generator
- **type**: skill — `app/media/thumbnail.py`
- **current impl**: 3 hand-templated concepts (`propose_concepts` from keyword extraction) → Pillow render (gradient bg + left/center text, stroke) → deterministic `_score` (clarity from word count, curiosity from "?", readability from length, fixed relevance/brand_fit).
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: text is composited by code, never rendered into the image by a model (avoids garbled Korean); 3 variants; scored.
- **weaknesses**: no saliency / face / subject detection for text-safe placement; scoring is a proxy formula with two constants literally hard-coded at 0.7; no CTR model; no A/B tracking hook.

### D12. Chart / Design
- **type**: skill — `app/media/chart.py` (matplotlib), `draw.py`
- **current impl**: matplotlib chart rendering for numeric scenes with verified sources; `draw.py` gradient/wrap helpers.
- **LLM**: no. **Det-possible**: yes (is).
- **weaknesses**: matplotlib default styling; chart type is inferred crudely; no brand palette.

### D13. Media QA / Content QA / Compliance QA
- **type**: skills — `app/media/media_qa.py`, `content_qa.py`, `compliance.py`
- **current impl**: `media_qa` — black/silence/duration/loudness/aspect checks via FFmpeg probes; `content_qa` — script/scene consistency, banned terms; `compliance` — policy floor, disclosure presence. Feed the scene-regen loop.
- **LLM**: content_qa partially. **Det-possible**: media_qa fully.
- **strengths**: real signal checks (not just "looks fine"); drive regen.
- **weaknesses**: loudness is a rough estimate (no EBU R128 `loudnorm` pass); no visual-quality (blur/artifact) check; compliance is keyword-based.

### D14. Scene Regeneration
- **type**: engine — `app/media/regen.py`
- **current impl**: targeted re-run of a single scene's visual/render when QA flags it; bounded attempts.
- **strengths**: surgical, not full re-render. **weaknesses**: no root-cause classification (regenerates the same way that just failed).

---

## E. Publishing (Phase 2)

### E1. Publisher Engine + Providers
- **type**: engine — `app/publishing/engine.py`, `publishers.py`, `base.py`, `mock_platform.py`, `client.py`
- **current impl**: `PublisherProvider` interface; capability vocabulary (SUPPORTED / AUTH_REQUIRED / APP_REVIEW_REQUIRED / ACCOUNT_TYPE_REQUIRED / LIMITED / MANUAL_ONLY / NOT_SUPPORTED / UNKNOWN); 10 platform providers over `MockPlatformAPI`; `DRY_RUN` default; official-API-first, no consent/verification bypass.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: honest capability model; no scraping; DRY_RUN; real adapters gated behind credentials.
- **weaknesses**: no real platform SDK wired (Meta Graph / YouTube Data / TikTok Content Posting all mock); capability table hand-maintained.

### E2. OAuth + Token Manager + Crypto
- **type**: service — `oauth.py`, `token_manager.py`, `crypto.py`
- **current impl**: OAuth state table, Fernet encryption (`ACF_MASTER_KEY`, key never in DB), `ensure_valid` refresh-once guard.
- **strengths**: encryption separate from DB; refresh loop guard. **weaknesses**: single Fernet key version in practice (Phase 5 added key-id support, not exercised).

### E3. Scheduler / Idempotency / Reconcile / Retry / DLQ
- **type**: services — `scheduler.py`, `idempotency.py`, `reconcile.py`, `retry.py`, `polling.py`, `verify.py`
- **current impl**: DB-driven due-time scheduler (UTC), `idempotency_key` unique (Phase 5 partial index), crash reconciliation (remote-verify before re-send), retry engine with attempt cap, remote status polling, post-publish verification. Phase 5 added `dead_letters` + non-retryable guard.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: genuinely production-shaped; exactly-once-ish via idempotency + verify; crash-safe.
- **weaknesses**: retry/backoff params are constants, not per-error-class policy objects; no saga/compensation across a multi-platform batch (each job independent — acceptable, but undocumented as a choice).

### E4. Normalizer / Preflight / Webhooks
- **type**: services — `normalizer.py`, `preflight.py`, `webhooks.py`
- **current impl**: media normalization to platform specs, preflight capability/asset checks, HMAC-verified webhooks with Phase 5 replay guard (`WEBHOOK_<state>` event dedup).
- **strengths**: preflight catches "can't post this here" before spending; signed webhooks + replay protection.
- **weaknesses**: normalizer re-encodes rather than validating-and-passing where already conformant.

---

## F. Analytics / Learning / Memory / Revenue (Phase 3)

### F1. Analytics Providers + Metric Catalog
- **type**: providers — `app/analytics/providers.py`, `mock_analytics.py`, `capabilities.py`, `metric_catalog.py`, `classify.py`
- **current impl**: `AnalyticsProvider` interface, capability-gated (**unsupported metric → null + status, never 0**), RAW + NORMALIZED, `MetricCatalog`.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: the "never fake a zero" rule is enforced; clean capability model.
- **weaknesses**: only a mock provider; no real YouTube Analytics / Meta Insights adapter.

### F2. Snapshot / Feature Store
- **type**: services — `snapshot.py`, `feature_store.py`, `schedule.py`
- **current impl**: time-series `analytics_snapshots` (window labels), `ContentFeature` store (hook_type, cta_type, durations, ai_video_ratio, scene variance, subtitle style, ai_slop, prompt_versions, topic_cluster + `topic_embedding`), collection schedule.
- **strengths**: proper time-series + feature rows; unique `(publication_id, window_label)` (Phase 5).
- **weaknesses**: features are hand-picked; `topic_embedding` is the 24-dim hashed vector (F7).

### F3. Performance Scoring / Baselines
- **type**: service — `performance.py`
- **current impl**: `ContentPerformanceScore` per objective; baselines = median / percentile; **channel-relative** performance; **outlier + data-anomaly flags** (`is_outlier`, `has_anomaly`) that exclude a row from learning.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: relative-not-absolute; outlier exclusion is a real false-learning guard.
- **weaknesses**: outlier test is simple (median-based); no seasonality/day-of-week normalization; no confidence interval on the score itself.

### F4. Revenue / Cost Ledgers
- **type**: services — `revenue.py`, `app/services/cost.py`, `budget.py`
- **current impl**: actual-vs-estimate revenue + cost ledgers; `check_budget` HARD gate (campaign/daily/monthly USD); per-agent cost logging.
- **strengths**: every LLM/search/media call is costed and budget-gated inline.
- **weaknesses**: revenue is mock; cost model for real media providers is a guess table.

### F5. Learning Engine
- **type**: engine — `app/learning/engine.py`
- **current impl**: **fully deterministic** pattern mining: group `PerformanceScore` by (platform, content_type), for each of 8 feature dimensions compute median lift vs channel baseline, apply a **false-learning guard** (`_consistent`: n<6 → drop best/worst, advantage must survive at 40%; n≥6 → ≥60% of the group on the same side of the median), `_confidence(n, lift, consistent)` → `upsert_memory`. Plus `_topic_fatigue`, `_creative_diversity` (pairwise similarity of last 8), `_prompt_version_perf`.
- **LLM**: **no**. **Det-possible**: yes (is).
- **strengths**: correlation≠causation enforced structurally; every memory carries evidence ids + n + confidence; no self-code-modification; explainable statements.
- **weaknesses**: fixed dimension list + bucket boundaries; median-lift only (no regression, no controlling for confounds — a `hook_type` win might just be topic mix); `_confidence` formula is hand-tuned; no drift detection; `_creative_diversity` similarity weights are magic numbers.

### F6. Memory (16 types)
- **type**: engine — `app/learning/memory.py`, `injection.py`
- **current impl**: `LearningMemory` rows, 16 `MEMORY_TYPES`, 5 `MEMORY_STATUS` (EXPERIMENTAL→STRONG→DEPRECATED); `status_for(n, confidence, consistent)` thresholds; `upsert_memory` keyed by (type, platform, content_type, topic_cluster, dimension); `deprecate_stale` (60d, unless pinned); `retrieve_memories` ranks by topic-cosine × confidence × recency, caps by `MAX_MEMORY_ITEMS` + `MAX_MEMORY_TOKENS`; `strategy_memory_context` injects as advisory text only.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: bounded retrieval (never dumps all), confidence + recency decay, dedup via upsert key, advisory-only injection, pinning, staleness deprecation. This is a real memory system.
- **weaknesses**: no episodic memory (specific past campaigns as retrievable episodes); no procedural memory beyond "recipes"; retrieval relevance leans on the 24-dim hashed embedding; `_TOK_PER_MEM = 60` is a fixed guess; no memory-conflict resolution (two MODERATE memories that disagree).

### F7. Embedding
- **type**: skill — `app/analytics/embedding.py`
- **current impl**: 24-dim hashed bag-of-normalized-tokens; Korean particle stripping + a ~20-entry hand synonym map; `cosine`, `assign_cluster` (centroid reuse ≥ threshold, else mint id from top stems).
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: offline, deterministic, zero-dep, good enough to catch obvious near-dupes; particle-aware.
- **weaknesses**: 24 dims + hashing = heavy collisions; synonym map is tiny and manual; **no real semantic similarity** ("AI가 바꾼 일자리" vs "고용 시장의 변화" won't match); every cluster/dedup/retrieval decision inherits this ceiling.

### F8. Experiment Engine
- **type**: engine — `app/learning/experiment.py`
- **current impl**: **sequential** experiments (labelled, not randomized A/B); `experiments` + `experiment_results` tables; confidence + sample-size gating.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: honest labelling ("SEQUENTIAL, not A/B"); tied to memory confidence.
- **weaknesses**: no bandit / Thompson sampling / power calculation; "which variant to try next" is not principled.

### F9. Recipe Engine
- **type**: engine — `app/learning/recipe.py`
- **current impl**: `content_recipes` — reusable parameter bundles derived from STRONG memories.
- **weaknesses**: thin; not versioned against outcomes the way §28 of the audit wants.

### F10. Opportunity Inputs / Injection / Reports
- **type**: services — `opportunity.py`, `injection.py`, `reports.py`
- **current impl**: prepares Phase-3 signals for Phase-4 scoring; strategy-memory injection; daily/weekly/monthly report builders.
- **strengths**: clean Phase 3→4 handoff. **weaknesses**: reports are template strings.

---

## G. Trend Intelligence / Opportunity / Autopilot (Phase 4)

### G1. Trend Providers + Capability Registry
- **type**: providers — `app/trends/*`
- **current impl**: 10 `TrendProvider`s (YouTube/GoogleTrend/WebSearch/News/Naver/Reddit/OwnAnalytics/TikTok/X/Threads) over a client abstraction; `capabilities.json` with `auth_status` from official docs; `OwnAnalyticsTrendProvider` always available (mines Phase 3 features); mock client = deterministic 60-topic catalogue; real `HttpTrendClient` raises `PERMISSION_MISSING`.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: honest capability gating; no scraping of API-less platforms; own-analytics evergreen path always works.
- **weaknesses**: every real source is mock; no multi-source signal fusion (each provider's events are scored independently, dedup only by hash).

### G2. Ingest
- **type**: service — `app/trends/ingest.py`
- **current impl**: scans active sources, writes `RawTrendEvent` with `sha256(source|normalized_topic)` 24h dedup, per-source isolation, reports skipped sources.
- **strengths**: one bad source never blocks others; dedup. **weaknesses**: dedup is exact-hash (normalized), not semantic; no cross-source "3 sources saw this → boost".

### G3. Signal Sub-scores
- **type**: skill — `app/autopilot/signals.py`
- **current impl**: **pure functions** 0–100: velocity (short/long interest ratio), acceleration (second difference), `trend_status` (BREAKOUT/RISING/…), `trend_type` + per-type TTL, freshness, competition, saturation (≠ competition), `risk_classify` (keyword categories + hint; ELECTION/MEDICAL escalate, TRAGEDY/MINORS → CRITICAL), difficulty, `natural_content_score`, `production_cost_estimate`, `fact_availability_score`.
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: pure, testable, explainable; risk escalation rules are conservative; TTL per trend type.
- **weaknesses**: **all thresholds/coefficients are hand-set** (`50 + (ratio-1)*55`, `accel*220`, …) with no calibration against real outcomes; `interest_series` shape comes from the mock; risk/difficulty are keyword lists (miss paraphrases, non-Korean); no proper time-series model (no STL, no changepoint, no burst statistic).

### G4. Dedup / Clustering
- **type**: skill — `app/autopilot/dedup.py`
- **current impl**: cluster via `assign_cluster` (F7 embedding, threshold 0.62); duplicate guard vs published topics over 7/30/90d → NEW/SIMILAR/DUPLICATE/NEW_ANGLE with a score penalty; excludes the candidate's own just-created campaign.
- **weaknesses**: inherits the F7 embedding ceiling; window scan is O(candidates × published) with re-embedding each call (no cache).

### G5. Opportunity Scorer
- **type**: engine — `app/autopilot/scoring.py`
- **current impl**: 17 dimensions → 0–100; bad dims inverted; per-objective weight tables (VIEWS/FOLLOWERS/REVENUE/PROFIT/BRAND/BALANCED) renormalized over present dims; per-platform tilt multipliers; `opportunity_formula_v1` stamped; explainable (component scores + reasons); two-stage (cheap Stage-1 → research precheck → full Stage-2).
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: explainable, objective-aware, two-stage keeps cost off weak candidates, formula versioned (so Phase 3 can evaluate it).
- **weaknesses**: **weights are hand-authored, never learned**; `calibration.py` nudges `TrendSource.value_score` but not the formula weights; platform tilts are guesses; no uncertainty on the final score.

### G6. Portfolio / Platform Select / Historical / Recheck / Watchdog / Calibration / Backtest
- **type**: engines — `portfolio.py`, `platform_select.py`, `historical.py`, `recheck.py`, `watchdog.py`, `calibration.py`, `backtest.py`
- **current impl**: CORE/TREND/EVERGREEN/REVENUE/EXPERIMENT mix + diversity guard + dynamic count + non-uniform budget + trend reserve; per-topic platform score threshold; historical/audience/revenue sub-scores from similar `PerformanceScore` rows (outliers excluded); pre-publish recheck (trend alive? dup appeared? → CONTINUE/UPDATE/HOLD/CANCEL, sunk cost ignored); watchdog (runaway cost / post limit / dup / QA-fail / auth-fail → PAUSED); calibration (predicted vs actual → SCORE_CALIBRATION memory + source value nudge); backtest (replay formula over past data — labelled a diagnostic).
- **LLM**: no. **Det-possible**: yes (is).
- **strengths**: genuinely thoughtful portfolio construction; sunk-cost rule; watchdog; calibration loop exists.
- **weaknesses**: calibration only tunes source weights, not scorer weights or signal coefficients; `historical` similarity uses F7 embedding; experiment slot in the portfolio isn't a bandit.

---

## H. Cross-cutting infra (Phase 5 — audited fresh)

### H1. Error Recovery / Durable Execution
- **current impl**: LangGraph Postgres checkpointer (journal + resume) for the two content graphs; Celery at-least-once; app-level idempotency keys + crash reconciliation (publishing); Phase 5 circuit breaker, DLQ + non-retryable guard, `JobLease` duplicate guard, stuck-job scan, retry with backoff (`call_with_retry` — hand-rolled, `tenacity` is a dep but barely used).
- **strengths**: the important guarantees (no duplicate campaign, no duplicate post) are enforced at the DB. Checkpointing is real.
- **weaknesses**: **three different retry mechanisms** (`providers/retry.py`, `publishing/retry.py`, Celery) with no shared policy; no saga/compensation layer for multi-step partial failure (autopilot produce→schedule); `tenacity` dependency is dead weight; durability config on LangGraph is default (no `durability="sync"` awareness).

### H2. Human Approval
- **current impl**: risk matrix in `autopilot/bridge.py` forces publish jobs to MANUAL for CRITICAL / SEMI_AUTO for HIGH; publish jobs have an approve step; ops flags need `confirm=true`.
- **weaknesses**: no `interrupt()`-style in-graph HITL pause/resume; approval is a DB state poll, not a first-class workflow signal.

### H3. Budget Guard / Scheduling / Observability
- covered above (F4, D-Celery, Phase 5 `/metrics` + `/admin`). Observability is solid post-Phase-5; scheduling is interval-beat not wall-clock.

### H4. Multi-Brand / Multi-Channel
- **status**: `VoiceProfile` is per-brand and `default_brand` exists; everything else is single-tenant. **This is Phase 6 — out of scope for this audit.**

---

## I. Advanced Video Studio  (`app/video/` — added 2026-08-31, Video Studio Upgrade)

Deterministic "Director" team layered onto the Phase 1-B media pipeline. 17
Engines, 0 LLM calls, 0 new dependencies. Runs inside `media_nodes.scene_plan`
(additive); output is a `VideoCreativePlan` on `PlatformContent.payload` +
per-scene hint keys + an advisory `video_qa`. Full design: `docs/VIDEO_ARCHITECTURE.md`.

| Component | Module | Status | LLM | Det | Note |
|---|---|---|---|---|---|
| Video Director | `video/director.py` | IMPLEMENTED | no | yes | orchestrates all Engines → `VideoCreativePlan` |
| Story Director + Emotional Arc | `video/story.py` | IMPLEMENTED | no | yes | beat-cue map (HOOK…CTA) + smoothed emotion curve |
| Retention Director + Boredom Detector | `video/retention.py` | IMPLEMENTED | no | yes | checkpoints + "reason to stay" + BOREDOM_RISK_SCORE; **no fake retention curve** |
| Shot Grammar + Continuity + Motion Energy | `video/shots.py` | IMPLEMENTED | no | yes | size/purpose per scene; SHOT_SCALE_REPETITION + A/B/A/B alternation flags |
| Pacing (refresh/density/load/focus/effect-budget/intent) | `video/pacing.py` | IMPLEMENTED | no | yes | visual-refresh band, cognitive-overload scenes |
| B-roll Director | `video/broll.py` | IMPLEMENTED | no | yes | 9-axis score + DIRECT/METAPHORICAL/… kinds + visual-evidence priority + "pretty-but-meaningless" penalty |
| Cinematic Image Motion | `video/motion.py` (+ `media/image_motion.py` delegate) | IMPLEMENTED | no | yes | 8 FFmpeg builders incl. `*_SIM` (honest, no depth model) |
| Voice Director V2 | `video/voice_plan.py` | IMPLEMENTED | no | yes | per-phrase prosody plan + VoiceConsistencyScore (brand band) |
| Audio / Sound Director | `video/audio_plan.py` | IMPLEMENTED | no | yes | music structure + anti-pump ducking envelope + SFX density + energy-follows-arc; loudness *profiles* (not claimed platform specs) |
| Color Director | `video/color.py` | IMPLEMENTED | no | yes | Pillow stats + gentle median match (non-destructive) + BrandColorLanguage |
| Edit Decision V2 / Timeline | `video/timeline.py`, `video/schema.py` | IMPLEMENTED | no | yes | frame-accurate, 7-track, non-destructive, edit history, overlap/gap flags |
| Video Quality Score V2 + Bad-Scene + Auto-Repair | `video/quality.py` | IMPLEMENTED | no | yes | 16 weighted dims; 11 bad-scene flags → repair-strategy map; `improved()` guards quality theatre |
| Video Skill Router + Quality Profiles + Fallback Ladder | `video/router.py` | IMPLEMENTED | no | yes | FAST/STANDARD/PREMIUM/CINEMATIC; GPU-gate → fallback |
| Video Skill Registry + versioning | `video/registry.py` | IMPLEMENTED | no | yes | 25 skills with status IMPLEMENTED/CODE_READY/DESIGN_ONLY |
| Editor Memory | `video/memory.py` | IMPLEMENTED | no | yes | style fingerprint into `LearningMemory(VISUAL, editor_style)` → repetition-avoid warning |
| Real ffmpeg QA probes | `video/ffmpeg_probe.py` | IMPLEMENTED | no | yes | ebur128 loudness, signalstats colour, freezedetect, A/V drift; **VMAF = CODE_READY** |
| Cut Engine V2 | `video/cuts.py` | IMPLEMENTED | no | yes | scored cut points (speech/phrase/beat/visual-change/emphasis/reaction/audio-onset); `MECHANICAL` fixed-interval flag |
| Caption Collision + selective emphasis | `video/captions.py` | IMPLEMENTED | no | yes | avoid face/chart/ui/safe-zone; ≤2 emphasis words; chars-per-second check |
| Creative QA V2 | `video/creative_qa.py` | IMPLEMENTED | no | yes | 12 checks (AI overuse / generic stock / repetitive zoom-captions-transitions / generic music / flat voice / weak arc / over-under-editing / visual mismatch / same-recent-format) |
| Smart Rerender graph | `video/rerender.py` | IMPLEMENTED | no | yes | per-stage input hashes → minimal rebuild set; subtitle-only change never rebuilds clips |
| Technical QA V2 (multipass) | `video/technical_qa.py` | IMPLEMENTED | no | yes | 7 passes on the real file via `ffmpeg_probe`; OK/WARN/FAIL/UNKNOWN |
| Video Studio dashboard + Retention Map | `frontend/app/campaigns/[id]/studio/page.tsx` + `GET /api/campaigns/{id}/media` (`creative_plan`, `video_qa`) | IMPLEMENTED | no | yes | design-signal retention map (not a predicted curve), scene direction, routed skills, 16-dim score, Creative/Technical QA |
| GPU/model adapters | `video/adapters/{models,reframe}.py` | CODE_READY | no | n/a | SAM 2 / Depth-Anything-V2 S/B/L / OpenCV tracking+reframe / NeMo diarization / WhisperX align / Real-ESRGAN / RIFE — each raises `OptionalSkillUnavailable`, never fakes; non-commercial weights hard-blocked |
| Kinetic captions | `media/subtitles.py::write_ass_kinetic` | IMPLEMENTED | no | yes | ASS `\k` from real word timings; assigned only on high-impact beats |
| Motion Graphics (Remotion) | — | DESIGN_ONLY | — | — | company licence ≥4 employees → not a hard dep; FFmpeg+Pillow graphics kept |
| Thumbnail Director V2 / Smart Screenshot / Preview Render / Retention Prediction / Human Edit Presets / Studio Dashboard | — | DESIGN_ONLY | — | — | specced in `VIDEO_ARCHITECTURE.md`; low value or needs real assets / Phase-3 data / frontend |

---

## Summary counts

| Area | Components | LLM-backed | Fully deterministic | Real (non-mock) external integration |
|---|---|---|---|---|
| Orchestration | 4 | 0 | 4 | Celery/Redis (real), LangGraph (real) |
| Research/Knowledge | 6 | 2 (research, fact-check) | 3 | Tavily adapter only |
| Content/Writing | 7 | 4 (strategy, hook, script, script-QA) | 3 | — |
| Media planning/render | 14 | 2 (scene plan, content-QA partial) | 11 | FFmpeg (real) |
| Publishing | 4 | 0 | 4 | none wired (all mock) |
| Analytics/Learning/Memory | 10 | 0 | 10 | none wired (all mock) |
| Trend/Opportunity/Autopilot | 6 | ~1 (topic extract) | 5 | none wired (all mock) |
| Infra (Phase 5) | 4 | 0 | 4 | Postgres, Redis, Prometheus text |

**Headline**: the system is already **deterministic-first** — only 8 genuine LLM
call sites (research, fact-check, strategy, hook, script draft, natural rewrite,
script-QA, scene plan), all logged + budget-gated. The audit's biggest targets
are therefore (1) the **research/fact-check depth** (single-query, snippet-only),
(2) the **24-dim hashed embedding** that bottlenecks all clustering/dedup/memory
retrieval, (3) **hand-tuned signal/score coefficients that are never calibrated**,
(4) **unfinished "optional real" paths** (WhisperX align stub, no real media/
publish/analytics adapters), and (5) **three un-unified retry mechanisms**.
