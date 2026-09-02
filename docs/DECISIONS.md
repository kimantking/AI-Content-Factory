# ARCHITECTURE DECISIONS

Only decisions that constrain future work. Newest last.

## D1 — LangGraph as the single Agent Runtime
`StateGraph` + Postgres checkpointer for durable, resumable execution. Concepts borrowed (not the libraries): Deep Agents (skills / sub-agents / context isolation), CrewAI (role/goal/task), MetaGPT (SOP), Mem0 (long-term memory). No second runtime.

## D2 — AI decides, code executes, DB remembers
LLM: research judgement, fact evaluation, strategy, hook, script, adaptation, SEO, learning. Plain code: DB, retry, queue, OAuth, API calls, FFmpeg, hashing, cache, validation, rate limit, scheduler, cost calc. Rendering is always code — the AI only emits an Edit Decision.

## D3 — Provider Adapter pattern
`LLMProvider`, `SearchProvider`, … Protocols in `app/providers`. Agents receive a provider via `registry.get_*()`; they never import a vendor SDK. `mock` implementations are deterministic and offline and are the default. Real adapters (`anthropic`, `tavily`) are opt-in via env + key.

## D4 — MOCK MODE is explicit, never disguised
`Settings.llm_is_mock` / `search_is_mock` are true when `MOCK_MODE=true`, provider is `mock`, or the key is missing. Mock output is labelled as such. A mock result is never reported as a production run.

## D5 — Fact gating
`KnowledgePack.verified_facts[*].status`. Only `VERIFIED` / `PARTIALLY_VERIFIED` may be stated as fact downstream. `qa_script` fails the campaign if an `UNVERIFIED` / `CONTRADICTED` fact text appears in the script. `fact_score = usable / total`; below `FACT_SCORE_THRESHOLD` routes to `research_fix`, capped at `RESEARCH_FIX_MAX` (no infinite loop).

## D6 — Checkpoint = Postgres, keyed by campaign_id
`PostgresSaver.from_conn_string(SYNC_DATABASE_URL)` where `SYNC_DATABASE_URL` is a **plain libpq DSN** (`postgresql://…`), distinct from `DATABASE_URL` (`postgresql+psycopg://…`) used by SQLAlchemy/Alembic. Checkpoint tables are created by `setup()` at runtime and are deliberately not managed by Alembic. `CHECKPOINTER_KIND=memory` exists only for fast unit tests that don't assert resume.

## D7 — Retry taxonomy
`TIMEOUT, RATE_LIMIT, AUTH_ERROR, BUDGET_EXCEEDED, INVALID_OUTPUT, PROVIDER_ERROR, INSUFFICIENT_RESEARCH`. `AUTH_ERROR` and `BUDGET_EXCEEDED` are non-retryable (`providers.errors.NON_RETRYABLE`). `call_with_retry` wraps provider calls; `INSUFFICIENT_RESEARCH` is additionally handled by the `research_fix` graph loop.

## D8 — Prompts live in files, versioned
`backend/prompts/<name>/v1.md`. Loaded + hashed by `services/prompts.py`, mirrored into `prompt_versions`. No long prompt literals in code.

## D9 — Celery + Redis, with configured app as current
`app/celery_app.py` builds the Celery app with the Redis broker and calls `set_current()`; `app/tasks.py` binds tasks with `@celery_app.task` (not `@shared_task`, which bound to the default AMQP app and failed silently). `app/main.py` imports `celery_app` so the API process enqueues to Redis. On Windows use `--pool=solo`.

## D10 — Budget Guard from Phase 1-A
`check_budget()` before every LLM call; sums `cost_logs` for campaign / rolling 24h / rolling 30d against `CAMPAIGN/DAILY/MONTHLY_BUDGET_USD`. Placeholder prices in `services/cost.py` — **replace with official pricing before enabling a paid provider.**

---

## MASTER DESIGN AMENDMENT — Natural Content Engine

Applies to all phases. Goal: content that reads as if a person planned and edited it (high quality, natural rhythm, editorial judgement) — **NOT** "AI-detection evasion". Platform-required AI disclosure is never removed; disclosure compliance is a separate system from the Naturalness Engine.

### A1 — Never fake authenticity
No injected typos, no deliberate grammar errors, no fabricated experience / anecdotes / interviews / quotes, no invented facts or numbers. "Human-like" = burstiness + specificity + editorial judgement + consistent voice.

### A2 — GitHub research before building; license first
Studied 9 repos (see `docs/OPEN_SOURCE_COMPONENTS.md` + `app/opensource/registry.json`). No repo copied. `usage_type ∈ {DIRECT_DEPENDENCY, REFERENCE_IMPLEMENTATION, ALGORITHM_REFERENCE, OPTIONAL_TOOL}`. Unclear license ⇒ `REFERENCE_ONLY`. Commercially sensitive: **Remotion** (paid Company License at 4+ employees), **Real-ESRGAN** / **RIFE** (model-weight terms), **edge-tts** (Microsoft ToS — dev/test only, never production default).

### A3 — Phase 1-A scope of the amendment: Writing only
Implemented now:
- `script_node`: `Draft Script → Natural Writing Pass → Fact Preservation Check`. If a usable fact or a number is lost, or an unusable fact appears, the pass reverts to the draft.
- `AI_SLOP_SCORE` (`naturalness/slop.py`): 0–100, weighted tells (uniform sentence length / low burstiness, repeated connectives, "중요합니다" spam, clichés & canned CTA, template openers, rigid triads, filler intensifiers, identical paragraph starts). `MAX_AI_SLOP_SCORE` default 20; `qa_script` fails above it.
- `VoiceProfile` (`naturalness/voice.py`): per-brand; loaded from `brands/<brand>/voice_profile.json`, else derived from `writing_samples/*.txt|md` (rhythm / question-frequency / formality heuristics — samples are analysed, never copied).
- Rotating CTA library (`naturalness/cta.py`): `question|save|share|follow|next_episode|comparison|none`; avoids the last 3 used types (tracked from recent `scripts.cta_type`).

Deferred to later phases (recorded so they aren't redesigned):
- **1-B**: Human Voice Engine (per-sentence performance plan), Editorial Rhythm Engine (content-driven scene-duration variation + cut margins 80–350 ms), Visual Naturalness (media-type mix + `VisualRepetitionScore → REPLAN_VISUALS`), Subtitle Naturalness (caption styles, limited highlight types, Korean phrase-unit line breaks), `AlignmentProvider` / `WhisperXAlignmentProvider` / `FallbackAlignmentProvider`, PySceneDetect boundaries, auto-editor silence/pause typing (`BREATH|EMPHASIS|DRAMATIC|UNNECESSARY`), optional Real-ESRGAN / RIFE quality chain (QA-before/after, revert if not better), multi-voice (narrator/quote), TTS provider scorecard (quality-first, not free-first).
- **2**: platform-native tone per platform; Naver Blog opener de-templating; `CreativeDirectorPass` (`FIX_REQUIRED`) before render.
- **3**: `NaturalnessScore` (writing / voice / visual diversity / edit rhythm / subtitle / originality / context relevance); Humanization Memory features (avg & variance of scene duration, voice speed variance, subtitle highlight freq, ai-video/stock/image-motion ratios, slop score) correlated with retention / shares / revenue; Learning must not conclude "be more AI".
- **4**: Autopilot topic selection also weighs naturalness features.
- **7**: Originality checks (hook/script/scene/thumbnail similarity, cross-platform sameness).
- **8**: Brand Voice settings UI + writing-sample upload.

### A4 — Multiple candidates only for high-impact, low-cost parts
Hooks / thumbnails / opening scenes may be N-up. Never render N full videos.

---

## PHASE 1-B — Media Production Engine

### D11 — Platform config is a single source of truth
`app/platforms/registry.py` holds every platform's aspect ratio, target duration,
styles, thumbnail flag, image count, storage dir. No platform string or aspect
ratio is hard-coded anywhere else; `get_platform()` also resolves dashboard
aliases ("YouTube Shorts" → `youtube_shorts`). Pinterest is two specs
(`pinterest_image`, `pinterest_video`).

### D12 — Media pipeline is a separate LangGraph subgraph
`app/agents/media_graph.py`, thread id `media:{campaign_id}` (distinct from the
Phase 1-A thread), Postgres checkpointer. It reads Phase 1-A outputs and refuses
to run unless `campaign.status == SUCCESS`. Node names never collide with state
keys (`run_media_qa`, not `media_qa`).

### D13 — Idempotent nodes = free crash/resume + scene regen
Every generation node checks the DB for an existing `SUCCESS` asset before doing
work (`_existing_scene_asset`, scene reuse in `scene_plan`, per-clip existence in
`render`). A killed worker resumes with `graph.invoke(None, cfg)` and regenerates
nothing that already succeeded. `platform_adapt` upserts `PlatformContent` instead
of delete-all so resume/regeneration keeps prior adaptations. Render/music/subtitle
assets are superseded (delete-then-insert per content) so re-runs don't accumulate
rows. A hand-set camera motion is marked `motion_effect="manual"` and the Visual
Director won't overwrite it.

### D14 — AI decides the visual, code makes it; cost drives fallback
`VisualDirector` (pure function) picks a `VisualType` per scene from the narration,
then downgrades along `VISUAL_FALLBACK` when the provider is unavailable, the
`MAX_AI_VIDEO_RATIO` cap is hit, or the media budget is short. Phase 1-B has **no
real VideoProvider** (`get_video_provider() → None`) and `MAX_AI_VIDEO_RATIO=0`, so
every AI_VIDEO request becomes AI_IMAGE + Image Motion. That is a **FALLBACK PASS**,
reported separately from an "AI video real generation" pass.

### D15 — Mocks produce real files, always labelled
Mock image = watermarked Pillow PNG. Mock TTS = real WAV whose duration matches a
syllable-rate estimate (so timing/subtitle/render run for real) with a near-silent
tone. Mock music = real WAV with explicit licence metadata. `Asset.provider_mode ∈
REAL|MOCK|DISABLED|ERROR`; DISABLED is surfaced (video). Never a mock reported as
REAL. No empty placeholder output files.

### D16 — Renderer: FFmpeg only, argument lists, libass-free subtitles
`run_ffmpeg` takes a list, never a shell string. Subtitles are burned in as
per-block Pillow RGBA overlays composited with `overlay=enable='between(t,…)'` —
no dependency on the ffmpeg build shipping libass, and full control of Korean text
+ highlight styling. BGM is ducked under narration with `sidechaincompress`
(static-volume fallback if that filter errors). `ffmpeg -i` stderr parsing +
`blackdetect`/`silencedetect` stand in for the missing `ffprobe`.

### D17 — Verifiable data only in charts; licence-safe music
`ChartSpec` without `source_ids` raises `ChartDataError` — the LLM never provides
numbers, only `visual_prompt` text. Compliance QA BLOCKs music whose
`commercial_use_allowed` is false or `license_type` is unknown, and BLOCKs
placeholder screen text.

### D18 — Word timing is honest, not fake forced-alignment
The estimator distributes the **real** audio duration across tokens by a
syllable/punctuation weight. It is labelled `estimator`, not `whisperx`. WhisperX
is a scaffold with a lazy import and a guaranteed fallback (Amendment §11).

### D19 — Media budget is a separate envelope
`check_media_budget` enforces `MEDIA_BUDGET_USD` on the sum of media-kind
`cost_logs`, then also calls `check_budget` so media spend counts toward the
campaign/daily/monthly limits. `BUDGET_EXCEEDED` stays non-retryable; scenes
already planned survive the stop and resume continues.

### D20 — Deferred to later phases (recorded so they aren't redesigned)
Real Image/Video/TTS adapters + `ProviderManager` wiring and a non-zero
`MAX_AI_VIDEO_RATIO`; Remotion renderer (paid Company License gate — FFmpeg-only
until animated captions/motion-graphics justify it); WhisperX alignment;
Real-ESRGAN / RIFE quality chain (QA-before/after, revert if not better);
auto-editor silence/pause-typing and PySceneDetect shot boundaries in the edit
engine; multi-voice; SFX sample library; Creative Director pass + NaturalnessScore
(Phase 3); per-queue scene-level Celery tasks; publishers (Phase 2).

---

## PHASE 2 — Multi-Platform Publishing Engine

### D21 — Official API first; capability, not assumption
`app/publishing/capabilities.json` (verified against official docs 2026-08-31, see
`docs/PLATFORM_CAPABILITIES.md`) is the authority for what each platform supports.
`publishing_status ∈ {SUPPORTED, AUTH_REQUIRED, APP_REVIEW_REQUIRED,
ACCOUNT_TYPE_REQUIRED, LIMITED, MANUAL_ONLY, NOT_SUPPORTED, UNKNOWN}`. No browser
automation to bypass a missing or ungranted feature. Naver Blog → `NAVER_BLOG_PACKAGE`
(manual); Naver Clip → `NOT_SUPPORTED` + manual package. Media-registry platform
keys resolve to publishing keys via `resolve_publishing_platform`.

### D22 — DRY_RUN is the default, and a mock is never a real pass
`DRY_RUN=true` by default: the engine builds account check + media validation +
payload + schedule but **never calls a publish API**. `PLATFORM_CLIENT=mock`
(default) uses the stateful offline `MockPlatformAPI`; `provider_mode=MOCK` rides
every result and Publication row. `PLATFORM_CLIENT=http` without a verified adapter
**raises `PERMISSION_MISSING`** — it never fabricates success. Integration status
per publisher stays `MOCK_TESTED` until real credentials move it forward.

### D23 — Credentials: encrypted, key out of the DB, masked in the open
Fernet (`cryptography`) encrypts access/refresh tokens at rest. The master key
comes from `ACF_MASTER_KEY` (env / secret manager) and is **never written to the
database**; unset → an insecure dev key with a loud warning. `mask_token` →
`abcd****1234` everywhere a token could surface (logs, API). The frontend never
receives a raw token.

### D24 — OAuth state is CSRF-safe and single-use
`oauth_states` rows: random `state`, PKCE `code_verifier`, `consumed` flag,
15-minute expiry. Replay or forged state → rejected. Token refresh happens
**exactly once** per publish attempt; `AUTH_REVOKED` → `REAUTH_REQUIRED`, never an
infinite retry.

### D25 — Idempotency + crash reconciliation = no duplicate posts
`idempotency_key = sha256(platform | account | content_id | scheduled_at |
media_hash)[:40]`. A job already in `UPLOADING/PROCESSING/PUBLISHING/VERIFYING/
PUBLISHED` is never re-published. Before every publish, `reconcile_job` asks the
platform (by idempotency key) whether a post already exists and **adopts** its
remote id instead of posting again. A duplicate post is a critical failure.

### D26 — PUBLISHED only after remote verification
A 200 is insufficient. `verify.verify_published` requires `get_remote_post` to
report a published/live state **and** a permalink. Webhooks
(`POST /webhooks/{platform}`) only advance a Publication when the HMAC-SHA256
signature verifies — an unsigned/forged webhook can never set `PUBLISHED`.

### D27 — DB-backed scheduler, UTC internally
All schedule state lives in `publish_jobs` (`scheduled_at` UTC, `timezone` for
display). `due_jobs(now)` is a pure query, so a backend / worker / Celery-beat
restart loses nothing. Beat `publish_scheduler_tick` (30 s) enqueues due jobs onto
the `publish` queue.

### D28 — Retry taxonomy with terminal states and a DLQ
`NETWORK_TIMEOUT/PROCESSING_ERROR/PLATFORM_UNAVAILABLE/UNKNOWN` → backoff retry
(30 s × 2ⁿ, cap 1 h); `RATE_LIMIT/QUOTA` → `RETRY_AFTER` (honour the platform
hint); `TOKEN_EXPIRED` → refresh then retry; `AUTH_REVOKED` → `REAUTH_REQUIRED`;
`PERMISSION_MISSING` → `BLOCKED`; `MEDIA_INVALID` → normalize once → retry;
`POLICY_REJECTION` → `BLOCKED` (no retry); `DUPLICATE` → no repost.
`attempt_count ≥ max_attempts` → `dead_lettered`, no further runs.

### D29 — Normalize into a new asset; polling is bounded
`normalizer.normalize_asset` re-encodes to the platform spec into a **new**
`Asset` with `meta.normalized_from` — the Phase 1-B original is never overwritten.
`PollingManager` runs the `[5,10,20,30,60]` s schedule up to
`PUBLISH_POLL_MAX_SECONDS` (900) then gives up with a `RETRY`, never spinning
forever.

### D30 — Isolation + append-only history
`run_publish_job` handles **one** job; a TikTok failure never cancels the YouTube
job (and one account's token problem never blocks another). `publication_events`
is append-only; `publish_audits` records who approved, the run mode, account,
schedule, API result, remote id, and failures. Campaign rollup: `ALL_PUBLISHED /
PARTIALLY_PUBLISHED / FAILED / IN_PROGRESS`. `publication_id` is the Phase 3 join
key and is already persisted.

### D31 — Deferred to later phases
Real per-platform HTTP adapters + token endpoints + media upload (needs
credentials); real OAuth token exchange/refresh; `MetaClient` Graph-version
registry as a shared HTTP layer; per-platform live rate-limit headers; publishing
cost accrual for paid APIs (X) beyond the capability note; Analytics/Learning
(Phase 3); AUTOPILOT run mode (Phase 4).

---

## PHASE 3 — Analytics / Learning / Memory / Revenue

### D32 — High views ≠ success; objective decides the score
`ContentPerformanceScore` is objective-weighted (`VIEWS / WATCH_TIME / RETENTION /
ENGAGEMENT / FOLLOWERS / REVENUE / PROFIT / BRAND / BALANCED`), with separate
short- vs long-form weight tables and `objective_config_version` stamped on every
row. Weights over metrics that are unavailable for a platform are **renormalized
out**. The Revenue Optimizer is just the `PROFIT` objective — a 300k-view /
130k-profit video can outrank a 1M-view / 30k-profit one.

### D33 — A metric the API can't give is null + a status, never 0
`AnalyticsCapability` (verified 2026-08-31, `docs/ANALYTICS_CAPABILITIES.md`)
drives `metric_catalog.normalize()`. Statuses: `AVAILABLE / UNAVAILABLE /
NOT_AUTHORIZED / NOT_APPLICABLE / NOT_READY`. Snapshots keep BOTH the untouched
`raw_payload` and the normalized columns. The real `HttpAnalyticsClient` raises
`PERMISSION_MISSING` rather than fabricate. TikTok watch-time/retention/revenue,
X organic metrics, LinkedIn member analytics, Naver everything → not synthesised
as API data (manual `CSV_IMPORT` / `MANUAL_IMPORT` path instead).

### D34 — Time-series snapshots, per-metric partial, provider-isolated
`collect_snapshot(pub, window)` is idempotent by `(publication_id, window_label)`;
a single-metric error → `PARTIAL`, a provider-wide error → a `FAILED` snapshot
row (never a lost snapshot). One platform's analytics failure never blocks
another's collection job. Snapshots are never overwritten — history is the point.

### D35 — Feature store: learn from *why*, not just *what*
`content_features` captures the content-side vector (hook type, duration, scene
count/variance, AI-video/stock ratios, subtitle style, CTA type, publish
hour/weekday, naturalness/slop, prompt versions, topic cluster + embedding). It is
joined to `PerformanceScore` for every learning query. Without it there is
nothing to learn from.

### D36 — Baselines are median/percentile; outliers & anomalies are quarantined
Channel baseline = median + p25/p75 per `(platform, content_type, metric)` (never
mean-only). `is_outlier` = 1.5·IQR fence; `DATA_ANOMALY` = a >50 % drop between
snapshots. Both are recorded on the score but **excluded from pattern
aggregation** so one viral clip cannot skew the model.

### D37 — Evidence-based learning; false-learning guard
Every `LearningMemory` carries `confidence`, `sample_size`, `evidence_ids`, and a
status (`EXPERIMENTAL / WEAK / MODERATE / STRONG / DEPRECATED`). `_consistent()`:
for n<6 drop the extreme point and require the advantage to survive; for n≥6
require a ≥60 % majority of the group on the same side of the baseline. One post,
inconsistent group, or tiny sample can never be `STRONG`. Also enforced:
**topic fatigue**, **creative diversity → `VARIATION_REQUIRED`**, and
prompt-version performance compared *within* a platform/slot, not as a blind
global mean.

### D38 — Memory is STRATEGIC GUIDANCE, injected, bounded — never FACT
`strategy_node` retrieves memories (relevance × confidence × recency), capped by
`MAX_MEMORY_ITEMS` and `MAX_MEMORY_TOKENS`, excluding `DEPRECATED`/`EXPERIMENTAL`,
and passes them to the Strategy step labelled "correlation, not fact; do not
override verified facts". The Knowledge Pack stays the single source of truth.
The AI never edits source code — only tunable preferences (strategy weights,
prompt selection, hook/duration/voice/subtitle/visual/thumbnail/CTA/publish-time
preferences, production profile, AI-video ratio, cost strategy).

### D39 — Exploration stays on; experiments are sequential and labelled
`EXPLORATION_RATIO` (80/20 default) keeps a slice of new options in rotation; a
new prompt/hook is never permanently excluded. `experiments` are
`SEQUENTIAL_EXPERIMENT` (not randomised A/B) with an effect-size + directional
confidence — labelled as directional, not causal. No RL / bandit machinery this
phase.

### D40 — Idempotent daily job; revenue actual vs estimate; provenance
`daily_learning_run` is idempotent by `run_date` (a crash-restart updates the same
row). `RevenueEntry` keeps `is_estimate` separate from actual and tags `source`
(`PLATFORM_API/AFFILIATE/SPONSOR/PRODUCT/MANUAL/ESTIMATE`). Every analytics /
revenue row records `source / retrieved_at / provider / raw reference`. Audience
data is aggregate-only — no PII.

### D41 — Deferred
Real per-platform analytics report endpoints + credentials; a real
`EmbeddingProvider` (currently a cheap hashing embedding); FX normalization for
mixed-currency profit; statistical significance (real p-values) and randomised
A/B; naturalness *causal* analysis; AUTOPILOT topic selection (Phase 4) — its
historical inputs (`opportunity_inputs`) are already produced.

---

## PHASE 4 — Trend Intelligence / AUTOPILOT

### D42 — Data-driven candidates, not AI daydreaming
Autopilot never "thinks up" a topic. It ingests `RawTrendEvent`s from real
sources (`docs/TREND_CAPABILITIES.md`), refines them into `TopicCandidate` angles,
and every candidate carries 17 measured sub-scores + an explainable Opportunity
Score. The goal is RIGHT topic/angle/platform/time/cost/quality — not maximum
volume. `AUTO_COUNT` can legitimately produce 0 when there is no strong
opportunity.

### D43 — Official/allowed sources only; approval status is not faked
`auth_status ∈ {AVAILABLE, AUTH_REQUIRED, APPROVAL_REQUIRED, LIMITED, DISABLED,
UNAVAILABLE}`. Google Trends (approval-gated alpha), TikTok/Threads (no discovery
API), X trends (paid tier) are never marked AVAILABLE and are **not scraped**.
The default scan set is OWN_ANALYTICS + AUTH_REQUIRED sources; the rest are
skipped and reported. The real `HttpTrendClient` raises rather than fabricate.

### D44 — HARD RULES are code-enforced and AI-immutable
`enforce_hard_rules()` rejects any change to daily/monthly hard budget, daily
post limit, blocked topics/keywords, compliance floor, or emergency stop unless
`actor == "user"`. A prompt asking to change one is rejected, not obeyed.
`apply_config` versions every change into `autopilot_config_versions`. The AI's
autonomous surface is only weights / memory / recipes / prompt selection /
thresholds / experiments / calibration — **never source code**.

### D45 — Trend ≠ Competition ≠ Saturation; bad dimensions invert
Velocity/acceleration are separated from absolute interest. Competition
(how contested) is separate from Saturation (how done-to-death). In the
Opportunity formula, competition/saturation/fatigue/risk/difficulty/cost enter as
`100 - x` so more is worse. Objective weight tables (VIEWS/FOLLOWERS/REVENUE/
PROFIT/BRAND/BALANCED) are renormalized over the dimensions actually present, and
`opportunity_formula_v1` is stamped on every candidate. Output is always
explainable (component scores + reasons + per-platform scores).

### D46 — Two-stage scoring; portfolio, not top-N
Stage 1 is a cheap pre-score (trend/freshness/dedup/basic competition) that culls
to `STAGE1_KEEP`; only survivors get the expensive Stage-2 (research precheck +
historical + revenue + originality + risk + cost + natural feasibility). Selection
is a **portfolio** (CORE/TREND/EVERGREEN/REVENUE/EXPERIMENT) with a diversity
guard, a dynamic count bounded by strong-opportunity availability, non-uniform
budget allocation, a held-back trend reserve, and FAST/STANDARD/PREMIUM profiles
(PREMIUM needs budget-allocator approval). FAST mode still runs Fact/Compliance/
Originality/Naturalness/Media QA — only the render is lighter.

### D47 — Reuse the existing pipeline; risk matrix overrides mode
`bridge.produce_from_context` calls `run_pipeline` (1-A) → `run_media_pipeline`
(1-B) → `create_jobs_for_campaign` (2). No new Research/Media/Publisher pipeline.
Idempotent by `candidate_id`. The risk matrix overrides the run mode: CRITICAL →
publish jobs MANUAL (never auto), HIGH → SEMI_AUTO, else per mode. A CRITICAL
topic is never auto-published even in FULL_AUTO.

### D48 — SHADOW = zero side effects; resumable; sunk cost ignored
SHADOW and SUGGEST_ONLY compute trends → candidates → scores → selection →
schedule → estimated cost and **create no campaign and publish nothing**. A run
is resumable by `resume_run_id` (portfolio returns the run's existing selections;
the bridge is idempotent → no duplicate campaigns). `pre_publish_recheck` can
`CANCEL` a produced-but-dead trend — sunk production cost is not a reason to
publish; the cancellation reason is stored.

### D49 — Watchdog + emergency stop
The watchdog pauses a run on runaway cost (vs HARD budget), too-many-posts,
duplicate campaigns, high QA-failure rate, or repeated auth failure. Emergency
STOP sets a hard flag (new runs refused), stops runs, cancels selected
candidates, and holds READY/SCHEDULED/QUEUED publish jobs — but **never touches a
job already UPLOADING/PROCESSING on a remote platform** (Phase 2 rule). PAUSE
lets in-flight work finish and starts nothing new.

### D50 — Score calibration feeds learning
Predicted Opportunity vs actual relative performance per produced candidate →
over/under-prediction → a `SCORE_CALIBRATION` learning memory + a nudge to each
`TrendSource.value_score`, so a source that historically produced bad picks is
de-weighted over time.

### D51 — Deferred (pre-Phase-5)
Real trend-source HTTP adapters + credentials; a real `EmbeddingProvider`;
wall-clock daily schedule (currently interval beat); true bandit allocation
(currently a labelled exploration ratio).

## Phase 5 — Production / Security / Backup / Monitoring / Recovery

### D52 — First-party ops primitives, zero new runtime dependencies
Metrics (`ops/metrics.py`), rate limiting (`ops/rate_limit.py`), circuit breaker
(`ops/circuit_breaker.py`), SSRF filter (`ops/ssrf.py`), secret redaction
(`ops/redaction.py`), structured logging (`ops/logging_config.py`) are all
implemented in stdlib. `/metrics` emits standard Prometheus 0.0.4 text so a real
Prometheus scrapes it unmodified. Rationale: keep the production image small and
auditable; every one of these libs would have added transitive deps for logic we
can own in <200 lines. OpenTelemetry and Sentry are **interface-reserved
no-ops** (`OTEL_ENABLED`, `SENTRY_DSN`) — opt-in when an endpoint exists.
See `OPEN_SOURCE_COMPONENTS.md` Phase 5 table.

### D53 — Backup = `pg_dump -Fc`, verified, restore-rehearsed into a separate DB
Daily `ops-daily-backup` beat: `pg_dump -Fc --no-owner --no-privileges` → sha256
→ `BackupManifest` → retention prune → `verify_backup()` (`pg_restore --list` +
checksum) → storage tar. The tool is resolved **setting → PATH → `docker exec
<postgres_container> pg_dump`** so it works whether or not the client is on the
host. `restore_to(backup_id, target_db)` **refuses the source DB**, always
restores into a separate database (`acf_restore_test` in CI), and re-verifies
`alembic_version` + table counts through a fresh engine. RPO design ≤ 24 h; a
tighter RPO needs WAL archiving on a real PG host (pgBackRest, MIT) — documented,
not bundled. No off-site copy is configured because no bucket/credentials were
supplied (`backup_destination` has an `s3` slot).

### D54 — Duplicate execution is stopped at the database, not in app logic
`job_leases` has a unique constraint `(job_kind, job_id, released)`;
`acquire_lease()` returns `None` if a live worker holds it and only reclaims
**expired** leases. Celery `worker_shutdown` releases held leases as `RECOVERED`;
`ops-stuck-job-scan` (120 s) releases expired ones and alerts. Combined with the
Phase 5 partial-unique indexes (`publish_jobs.idempotency_key`,
`publications.publish_job_id`, `analytics_snapshots (publication_id,
window_label)`) and the webhook `WEBHOOK_<state>` replay check, a crash or a DB
restore cannot produce a double post.

### D55 — Runtime flags persist in the DB and gate the app at the middleware
`EMERGENCY_STOP` / `SAFE_MODE` / `MAINTENANCE_MODE` live in `runtime_settings`
(3 s read cache) with an `AuditEntry` on every change. `MAINTENANCE_MODE` → 503
for app routes at `OpsMiddleware` (health/metrics/ops exempt). `SAFE_MODE` →
autopilot production HOLD. `EMERGENCY_STOP` is also mirrored from
`autopilot/emergency.py` so it survives a process restart. Only `actor="user"`
paths may enable a mode; the ops API requires `confirm=true`.

### D56 — Production boot fails closed on unsafe config
`ops/env.py::validate_environment()` runs at `app/main.py` import and **raises**
in production for missing `SECRET_KEY` / `ACF_MASTER_KEY`, `CORS_ALLOW_ORIGINS`
or `TRUSTED_HOSTS` left as `*`, or a `localhost` OAuth callback. Non-prod only
warns. A misconfigured prod deploy does not start rather than starting insecure.

### D57 — `/api/ops/*` has no built-in auth; it relies on the deployment front door
The ops + health routers are unauthenticated by design (health/metrics must be
scrapeable; ops actions are `confirm`-gated and audit-logged). A real deployment
puts proxy auth / SSO / network isolation in front of `/api/ops/*` and `/admin`.
Recorded as a known limitation in `PRODUCTION_READINESS.md` and
`DEPLOYMENT_CHECKLIST.md`.

### D58 — Docker production overlay, not a rewrite
`docker-compose.prod.yml` layers over the dev compose: `APP_ENV=production`, no
source bind-mounts / reload, `restart: unless-stopped`, per-service resource
limits, non-root image (`USER appuser` uid 10001, `no-new-privileges`),
Postgres/Redis ports unpublished, `${VAR:?}` guards that refuse to start without
real secrets, Celery **queue-split** workers (`worker` core+publish+beat /
`worker-media` / `worker-analytics` / `worker-autopilot`), and an **optional**
Caddy TLS `proxy` profile. `docker compose config` validates.

### D59b — GitHub Best-of-Breed Audit (2026-08-31): what changed, what didn't
A full audit of every agent/engine/skill/provider against the current OSS
ecosystem (`docs/AGENT_SKILL_INVENTORY.md` + `docs/BEST_SKILL_MATRIX.md`).
Finding: the system is already **deterministic-first** (only 8 real LLM call
sites) and its production guarantees (no duplicate campaign/post, capability-honest
analytics, false-learning guard) are sound. Three low-risk improvements applied in
code (D60); everything higher-leverage is logged as RECOMMENDED / RECOMMENDED_FOR_LATER
with a concrete plan, **not applied**, because the regression surface is too large
to bundle with an audit. No new runtime dependency was added. LangGraph stays the
single runtime (no CrewAI/AutoGen/Temporal/DBOS — spec §10/§24). AGPL projects
(SearXNG, Firecrawl core, Postiz) are barred as linked dependencies.

### D60 — Audit improvements applied in code (low-risk, evidence-backed)
1. **`parse_json` tolerant extraction** (`app/agents/common.py`): strips
   ` ```json ` fences and falls back to a balanced-brace scan before failing.
   No-op for valid JSON (the mock), so zero behaviour change today; real LLM
   adapters that wrap JSON in prose now parse. Idea from `instructor`/`outlines`,
   no dependency.
2. **Research fix-pass query decomposition** (`app/agents/nodes.py::_fix_query`):
   the research retry used one fixed string; it now rotates through three
   angle-varied queries (statistics → counter-evidence → primary/recent), one per
   pass, so search-call count and cost are unchanged. First concrete piece of the
   gpt-researcher / STORM query-decomposition pattern; the full first-pass
   sub-query fan-out is RECOMMENDED (needs cost-assert fixtures updated).
3. **Full-jitter exponential backoff** (`app/providers/retry.py`): fixed linear
   `sleep(base_delay*i)` → `sleep(_JITTER.uniform(0, base_delay*2**(i-1)))` (AWS
   "Exponential Backoff and Jitter") to avoid synchronised retry storms against a
   real API. Uses a **dedicated `random.Random()` instance** (`_JITTER`), NOT the
   global `random` module — because `app/learning/experiment.py` falls back to the
   global RNG when unseeded, and a first cut using `random.uniform` perturbed that
   sequence during fault-injection tests, cascading into 3 order-dependent
   `tests/ops/` failures. Isolating the RNG fixed it; a library must never consume
   the process-global RNG.
All three: targeted test `tests/test_agents_common.py` (7) + full regression
**172 passed** (`-p no:randomly`), re-run twice for anti-flake confidence.

### D61 — Highest-leverage deferred item: real embeddings behind a provider
`app/analytics/embedding.py`'s 24-dim hashed bag-of-tokens is the ceiling on
every cluster / dedup / memory-retrieval / topic-fatigue / creative-diversity
decision in Phase 3 & 4. Plan (own task, not this audit): add an
`EmbeddingProvider` Protocol; `HashedEmbeddingProvider` (current) stays the test
default; `Model2VecEmbeddingProvider` (`model2vec`, MIT — real multilingual
static embeddings, **no torch**) is the opt-in real path; re-baseline the
analytics + autopilot fixtures and re-tune the `assign_cluster` threshold.
`fastembed` (Apache-2.0, ONNX) is the alternative. `sentence-transformers` is
rejected for this (drags ~1GB torch for no gain over model2vec).

### D62 — New capability planned: SkillRegistry + SkillRouter (spec §26–§29)
Not built yet. A thin metadata + gating layer over the existing LangGraph nodes
(no framework): `SkillRegistry` (`skill_id, version, category, requires_llm,
estimated_cost, estimated_latency, dependencies, fallback, quality_impact,
enabled`) and a `SkillRouter` (`task, content_type, platform, risk, budget,
quality_profile` → `{required, optional, skipped}`). Skill version tags
(`hook_generation_v2`, …) join `prompt_versions` on `ContentFeature` so Phase-3
Analytics can measure a skill change's effect. `ARCHITECTURE_PATTERN` from
LangGraph conditional routing. Scoped change, not an audit-pass edit.

## Video Studio Upgrade — Advanced Video Studio (2026-08-31)

### D63 — Advanced Video Studio is a deterministic Director layer, additive to the pipeline
New package `app/video/` (17 modules): Video Director + Story / Retention /
Boredom / Shot-Grammar / Pacing / B-roll / Cinematic-Motion / Voice-V2 / Audio /
Colour / Timeline(EditDecision V2) / Quality-V2 / Router / Registry / Editor-Memory
Directors, plus `adapters/` (CODE_READY GPU skills) and `ffmpeg_probe.py` (real
ebur128 / signalstats / freezedetect / A-V-drift / libvmaf). **Zero new runtime
dependency.** All Directors are pure/deterministic Engines — the video path still
has only 3 LLM calls (platform_adapt, scene_plan, edit_decision). It runs *inside*
the existing `scene_plan` node (no new LangGraph node → no checkpoint-topology
change) and is strictly **additive**: it enriches scene dicts with hint keys and
stores a `VideoCreativePlan` on `PlatformContent.payload["creative_plan"]`; it
**never overwrites** `camera_motion` / duration / `visual_type`, so the Phase 1-B
regression is unaffected. `media_qa_node` gains an advisory `video_qa`
(`VideoQualityScoreV2`, 16 dims + bad-scene detection) that never blocks persist.

### D64 — Cinematic motion is simulated and labelled as such; no fake retention numbers
`app/video/motion.py` builds 8 FFmpeg image-motion filters incl.
`DEPTH_PARALLAX_SIM / DOLLY_IN_SIM / FOCUS_PULL_SIM / SLOW_ORBIT_SIM`. No depth
model is used, so these carry the `_SIM` suffix and gentle rates (no over-done
fake camera). `image_motion.render_scene_clip` delegates only the cinematic
motions to this builder; the legacy 7 motions are untouched. Retention analysis
(`retention.py`) reports *design* signals ("reason to stay" per checkpoint,
boredom-risk, open loops) and explicitly emits **no predicted retention curve**
while Phase-3 retention data is thin (spec B94). Enhancements (upscale/interp)
count as improvements only via `quality.improved(before, after, min_gain)` — no
"quality theatre" (spec B67).

### D65 — Video OSS licence gate: code licence ≠ model licence; non-commercial is blocked
Every video component was checked on **both** its code and its model/weight
licence (`docs/OPEN_SOURCE_COMPONENTS.md` register, `VIDEO_BEST_SKILL_MATRIX.md`).
Blocked from Production: **CoTracker** (CC-BY-NC-4.0), **Depth-Anything-V2 Giant**
(CC-BY-NC-4.0 — `adapters/models.depth_map` hard-rejects `model_size="giant"`),
**Spotify/pedalboard** (GPL-3 — would infect a closed service; use FFmpeg audio
filters), **Remotion as a hard render dep** (company licence ≥4 employees —
DESIGN_ONLY, keep FFmpeg+Pillow), non-commercial **RIFE** weights (verify).
Commercial-safe: SAM 2 (Apache-2.0 code+weights), Depth-Anything-V2 S/B/L
(Apache-2.0), faster-whisper (MIT) / WhisperX (BSD-2), NeMo / SpeechBrain
(Apache-2.0, ungated — preferred over gated pyannote), OpenCV ≥4.5 (Apache-2.0),
VMAF (BSD+Patent). Heavy skills are `OptionalSkillUnavailable`-raising adapters
with deterministic fallbacks routed by `app/video/router.py`; the app runs fully
on CPU with no models installed.

### D66 — Video Skill Router + Quality Profiles so not every skill runs every time
`router.route(...)` → `{required, optional, disabled, fallbacks, reasons}` from
`(platform, content_type, profile, budget, risk, opportunity, gpu_available,
is_short, multi_speaker)`. Profiles FAST / STANDARD / PREMIUM / CINEMATIC gate
skills by a per-skill min-rank; GPU skills are only `required` when a GPU worker
is declared, else routed to a fallback ladder; CINEMATIC is flagged as needing
budget-allocator approval. `VideoSkillRegistry` carries `version / algorithm /
dependencies / fallback / quality|cost|latency impact / status
(IMPLEMENTED|CODE_READY|DESIGN_ONLY)` so Phase-3 Analytics can later attribute
retention to a skill version.

## Best-of-Breed + Video Studio — continuation (2026-08-31, part 2)

### D67 — Install policy: project-scoped only; global tools / user plugins are last resort
Priority for any capability gap: (1) improve existing code → (2) architecture
pattern → (3) implement the algorithm → (4) project-scoped dependency
(`requirements.txt` / `package.json`) → (5) optional adapter → (6) global tool →
(7) user-scope Claude plugin. 6 and 7 are not used without a specific, approved
reason. The externally-suggested `DietrichGebert/ponytail` / `@ponytail` /
`graphify` / `headroom-ai[proxy,mcp]` are **not installed** — not needed by this
project. This whole pass added **0 new dependencies** (project- or global-scoped).

### D68 — Audit results classified A/B/C; the A-tier was actually implemented
- **A. IMPLEMENT_NOW** (done in code + tests this pass):
  - Research Agent — first-pass **query decomposition** (`app/agents/research.py::expand_queries`, 3 complementary sub-queries), **merge + rank** by domain authority × topical match × freshness + **domain diversity** cap, **contradiction discovery** (`find_contradictions`), **coverage score** as a second stopping signal. Fix pass keeps its 1-query angle rotation.
  - Fact Checker — **atomic claim extraction** (`app/agents/factcheck.py::atomic_claims`, splits on clause boundaries, no-op on a claim with none), **check-worthiness** filter, **cross-source agreement count**, **temporal-marker** extraction, **confidence re-blend**, lone-source `VERIFIED → PARTIALLY_VERIFIED` downgrade (`enrich_facts`).
  - Hook Agent — **multi-candidate diversity filter** (cosine, `min_keep` floor), **recent-hook similarity penalty**, **platform-aware re-rank**, **factual-exaggeration guard** (absolute-claim + unbacked-number flags; time-span numbers like "3년간" excluded).
  - Memory retrieval — **keyword-overlap fusion** boost added to the existing single-score rank (Mem0-style multi-signal), cap + DEPRECATED filter untouched.
  - Video: **Cut Engine V2** (`app/video/cuts.py`), **Caption Collision + selective emphasis** (`captions.py`), **Creative QA V2** 12-check (`creative_qa.py`), **Smart Rerender dependency graph** (`rerender.py`), **Technical QA V2 multipass** on the real file (`technical_qa.py` via `ffmpeg_probe`), **pause classification** BREATH/EMPHASIS/DRAMATIC/UNNECESSARY (`voice_plan.classify_pause`), **cognitive-load reduce actions** (`pacing.reduce_actions`), **quality score 0–100 + `plan_repairs` + `continuity_score`** (`quality.py`).
- **B. OPTIONAL_ADAPTER** (CODE_READY, needs GPU/model/API — never faked): SAM 2 segmentation, Depth-Anything-V2 S/B/L parallax, OpenCV tracking, NeMo/SpeechBrain diarization, WhisperX alignment, Real-ESRGAN / RIFE, VMAF (ffmpeg libvmaf). All in `app/video/adapters/` + `ffmpeg_probe`, routed to a deterministic fallback by `router.py`.
- **C. DEFER** (complexity/risk vs benefit now): unify all retry on `tenacity` (the three retry mechanisms already pass — pure refactor risk); real semantic embeddings behind `EmbeddingProvider` (D61 — full Phase 3/4 fixture re-baseline); `pybandits` experiment engine; `ruptures`/STL trend signals + scorer-weight calibration; real motion-graphics via Remotion (company-licence-gated); Encoding-profile CRF switch in the renderer; auto-editor/PySceneDetect cut logic (needs real footage).

### D69 — Agent-core upgrades are additive and no-op on mock data
`atomic_claims` only splits a claim that has a clause/conjunction boundary — every
mock candidate fact passes through unchanged, so the deterministic mock pipeline
and its assertions are unaffected; the benefit appears with real research output.
`expand_queries` raises the first-pass search-call count from 1 to 3 (mock search
returns results for any string; `CostLog` count assertions are `>=`).
`enrich_facts`' lone-source downgrade can only move `VERIFIED → PARTIALLY_VERIFIED`
— both count as "usable", so `fact_score` never drops below the gate. Hook
`diversity_filter` has a `min_keep=3` floor so pruning can't starve the picker
(`Hook count >= 3` holds). New agent modules: `app/agents/{research,factcheck,hooks}.py`;
tests: `tests/test_agent_core_upgrades.py` (11).

### D70 — Video Studio dashboard + retention map: structure only, no fake numbers
`GET /api/campaigns/{id}/media` now returns `creative_plan` + `video_qa` (from the
primary content payload). New page `frontend/app/campaigns/[id]/studio/page.tsx`
renders the story arc, a **retention map of design signals** (checkpoints +
high-impact scenes on the timeline — explicitly labelled "not a predicted
curve"), scene-direction table, routed skills, the 16-dim quality score, Creative
QA, and Technical QA verdicts. `tsc` + `next build` clean.

## Phase 6 — Multi-Brand / Multi-Channel / Portfolio / Monetization (2026-09-01)

### D71 — Security first: auth + tenant isolation before multi-brand features
`app/auth/` — local users, stdlib-pbkdf2 password + HMAC-keyed API-key hash (no
SaaS auth dependency). `OpsMiddleware` 401s `/api/ops/*`, `/api/admin/*`, `/admin`
when `APP_ENV in (production, staging)` or `AUTH_ENFORCE=true`; open in dev/test so
the existing suite is unchanged. RBAC: OWNER>ADMIN>PUBLISHER>EDITOR>ANALYST>VIEWER
with capability→min-role (`app/auth/context.py`). Every workspace-scoped resource
is fetched+checked in `app/mb/scope.py` (403 on cross-workspace id — no IDOR).
Full model + proofs: `docs/SECURITY_MODEL.md`.

### D72 — Additive schema only; NULLABLE tenant columns on legacy tables
Migration `0007_multibrand`: 20 new tables + `ADD COLUMN IF NOT EXISTS`
(NULLABLE) `workspace_id/brand_id/channel_id` on `campaigns / platform_accounts /
cost_logs / revenue_entries`. `Base.metadata.create_all(tables=[…])`, no
destructive DDL (spec §105). Legacy rows keep NULL scope = "pre-Phase-6"; the
223-test pre-Phase-6 suite is unaffected. `tests/conftest.py::_DOMAIN_TABLES`
extended with the new tables (child-first) for isolation.

### D73 — Hierarchical hard budget with transactional reservation
`app/mb/budget.py` — Workspace ⊇ Brand ⊇ Channel ⊇ Campaign. `reserve()` runs the
limit check + insert inside one transaction that `SELECT … FOR UPDATE`-locks the
day's reservation rows for the scope, so concurrent workers cannot collectively
exceed a hard limit. `settle()` rewrites the reservation to the actual cost;
`release()` frees it. Proven by a 2-thread race test
(`tests/mb/test_budget.py::test_concurrent_reservations_cannot_exceed_hard_limit`).

### D74 — Credential scope isolation
`token_manager.assert_credential_scope(account, expected_workspace, expected_brand,
expected_platform)` raises `PublishError(AUTH_REVOKED)` on mismatch; called by
`ensure_valid()`. Brand A's Instagram token can never be used by Brand B's
publisher. Legacy NULL-scoped accounts pass only when no expectation is given.

### D75 — Channel & Portfolio managers are deterministic; AI recommends, never deletes
`channel_manager.py` / `portfolio.py` compute health (0–100, objective-weighted),
operating plans, portfolio scores, and budget allocation from SQL/metrics/rules —
**no LLM per cycle** (spec §102). Scale status uses the **median** of non-outlier
performance scores so one viral clip cannot trigger `SCALE` (§114); warmup /
low-sample channels are weight-dampened so a lucky month can't 5× a budget (§93).
`allocate_budget` is **hard-capped** to the workspace daily limit and keeps a
per-channel **exploration floor** (§98). `recommendations()` emits advisory
`portfolio_decisions` (evidence + confidence + sample_size, `applied=False`) and
**never** `DELETE`/`ARCHIVE` — the user decides (§52). LLM is reserved for
reposition strategy (DESIGN_ONLY).

### D76 — Monetization: estimate ≠ actual; safety guards over revenue
`monetization.py` — `profit_center` returns `revenue_actual_usd` and
`revenue_estimated_usd` in **separate** fields, never summed (§27/§115). Guards:
`sponsor_content_guard` BLOCKs a paid requirement that collides with facts /
compliance / brand policy (a deal never overrides Compliance — §49);
`commercial_guards` BLOCKs fake scarcity / social proof / hidden ads / fake
discounts (§65) and warns on high sponsored/commercial density;
`enforce_affiliate_disclosure` **adds** a missing disclosure, never removes one
(§32/§117).

### D77 — Phase 6 scope: core loop done + tested; long tail is DESIGN_ONLY
Delivered: auth + RBAC + tenant/credential isolation + hierarchical budget +
Channel/Portfolio managers + routing/cannibalization + Monetization guards + a
`/portfolio` dashboard + a multi-channel mock e2e + brand/channel/workspace pause,
all additive with the full regression green. DESIGN_ONLY (schema/engine hooks
exist, surface is a follow-up): full sidebar dashboard IA, cross-channel
scheduler + capacity planner + production-slot queue, channel/portfolio autopilot
beat wiring, reposition strategy (LLM), new-channel wizard, brand/channel
cloning, report generators, load-test fixtures, asset library UI + template
system, strict worker-job tenant validator, full audit-log coverage of Phase-6
mutations. **No new dependency** (project- or global-scoped); install policy D67
upheld (`ponytail`/`graphify`/`headroom-ai` not installed).

### D59 — What Phase 5 does NOT claim
Per the Phase 5 production rule: no real production server address, domain, SSL
cert, cloud credential, or SNS production credential was provided. Off-site/S3
backup, WAL/PITR, external alert channels (email/Slack/PagerDuty), OTel/Sentry
export, TLS issuance, and log aggregation are **CODE READY / LOCAL-STAGING
VERIFIED / NEEDS_PRODUCTION_ENVIRONMENT** — interfaces and profiles exist and are
exercised locally, but are not verified against live infrastructure. They are not
reported as PASS.

### D78 — Phase 7 Content Governance is deterministic; no LLM produces a verdict
`app/governance/` decides ALLOW / ALLOW_WITH_DISCLOSURE / ALLOW_WITH_ATTRIBUTION /
FIX_REQUIRED / HUMAN_REVIEW / BLOCK from metadata, hashes, the rights ledger,
licence/policy registries, regex guards and the cheap embedding — never an LLM
"probably fair use" guess (spec §0). Unclear rights ⇒ `UNKNOWN_RIGHTS` ⇒ hard
block from FULL_AUTO / AUTOPILOT / SEMI_AUTO auto-publish. Docs:
`CONTENT_GOVERNANCE.md`, `RIGHTS_LEDGER.md`, `ORIGINALITY_ENGINE.md`,
`CONTENT_POLICY_CAPABILITIES.md`, `AI_DISCLOSURE.md`, `COPYRIGHT_RESPONSE.md`.

### D79 — Governance is wired into the Publisher and Autopilot, and fails safe
`publishing/engine.run_publish_job` calls `govern_pre_publish` after the token
check and before preflight; `autopilot/bridge.produce_from_context` calls
`govern_campaign(stage="post_render")` after the pre-publish recheck. A
non-publishable verdict → job `BLOCKED` / `WAITING_APPROVAL` (never the platform
call) and candidate `GOVERNANCE_HOLD` (no jobs created). Any exception inside
governance ⇒ `HUMAN_REVIEW` + `publishable:false`, never a silent pass. Master
switch `GOVERNANCE_ENFORCE` (default true). A pre-Phase-7 campaign
(`workspace_id IS NULL`, no ledger) short-circuits to
`GOVERNANCE.NOT_APPLICABLE_LEGACY` so the legacy suite stays green; new flows
always create a ledger.

### D80 — Hard governance blocks cannot be cleared by a UI approval or an agent
`decision._HARD_BLOCK_CODES` (unknown-rights-in-auto, expired, watermark, blocked,
platform-restricted, voice-clone-no-consent, copyright-block, high-risk-PII,
chart-mismatch, public-figure-endorsement, originality-duplicate).
`apply_human_override` returns an error for any of them; a soft `HUMAN_REVIEW` /
`FIX_REQUIRED` is clearable by an authorised reviewer. State machine
(`_TRANSITIONS`) rejects invalid transitions; `BLOCKED` leaves only via a real
fix (`SCANNING`) or authorised `RESOLVED`.

### D81 — Phase 7 adds no dependency; C2PA and heavy perceptual hashing declined
Perceptual hashing is aHash+dHash via the existing Pillow (`governance/phash.py`).
C2PA / Content Credentials signing (`c2pa-python`) is investigated and **not
adopted** — needs a signing identity + trust list + native bindings, few
platforms verify CR for short-form, and the internal `RightsManifest` +
`AssetLineage` already record provenance; generating a fake Content Credential is
refused (OPTIONAL, revisit when a signing identity + a verifying platform both
exist). PII detection is regex-floor + OPTIONAL adapter (absent ⇒ route to
review, never a faked pass). Install policy D67 upheld;
`ponytail`/`graphify`/`headroom-ai` not installed.

### D82 — Additive schema for Phase 7 (migration `0008_governance`)
14 new tables + NULLABLE columns `platform_contents.governance_state` /
`.governance_decision`, `publish_jobs.governance_decision` / `.disclosure_meta`
(ORM-mapped in `models.py`, DDL in `models_gov.GOV_ALTERS`). `policy_registry` /
`license_registry` are fixture tables re-seeded per test;
`tests/conftest.py::_DOMAIN_TABLES` extended with all 14 (child-first) for
isolation. `PolicyRegistry.action` is `VARCHAR(28)` (holds
`PLATFORM_FIELD_REQUIRED`). Platform policy rows are **fixtures modelling the
shape** of each platform's rules with `source_reference` + `last_verified_at`;
real current-policy verification is `NEEDS_PRODUCTION_ENVIRONMENT` /
`LEGAL_REVIEW_REQUIRED` (`CONTENT_POLICY_CAPABILITIES.md`).

### D83 — Cross-Phase Intelligence Upgrade reuses the pipeline; deterministic; 0 deps
URL Learning / Reference Dataset / Prompt Distillation / Agent Skill Learning /
SNS Platform Selection live in `backend/app/intel/` and reuse Research / Fact
Check / Memory / Learning / Video Studio / Governance / Publisher / Analytics —
no new runtime architecture. Migration `0009_intelligence` (13 tables + NULLABLE
`campaigns.execution_mode` / `.platform_selection_locked`,
`publish_jobs.platform_selection_mode`, all ORM-mapped). **0 new dependencies**
(stdlib `html.parser` for extraction, existing Pillow / `app.analytics.embedding`
for hashing/similarity). Docs: `URL_LEARNING_ENGINE.md`, `LEARNING_STUDIO.md`,
`REFERENCE_DATASET.md`, `PROMPT_DISTILLATION.md`, `LEARNED_SKILLS.md`,
`PLATFORM_SELECTION.md`, `REFERENCE_LIBRARY.md`.

### D84 — LEARN_ONLY / REFERENCE_ONLY can never do production work
`intel/modes.assert_no_production_side_effects` raises `ProductionSideEffectBlocked`
for campaign production / AI image / AI video / TTS / final render / PublishJob /
SNS API call. `create_jobs_for_campaign` returns `[]` for a LEARN_ONLY campaign and
`run_publish_job` blocks it. `REFERENCE_ONLY` stores the reference but writes no
dataset / prompt / memory. Proven by `tests/intel/test_learn_only.py` (no Campaign
/ Asset / MediaTask / PublishJob rows created).

### D85 — External URL content is UNTRUSTED; prompt injection is data, never executed
`intel/injection` detects and strips "ignore previous instructions" / "run this
command" / "reveal API key" / "delete database" / "change system prompt" (EN+KO)
before any LLM sees the text; nothing from a reference is executed. SSRF reuses
the Phase 5 guard with per-redirect-hop re-validation; production keeps the full
DNS-rebinding check, non-production skips a blocking lookup for unresolved hosts.
The JS-rendering `BrowserFetchAdapter` is off by default (`browser_fetch_enabled`,
install policy D67 — Playwright pending approval) and its stub raises rather than
faking a render. No adapter bypasses CAPTCHA / paywall / login / DRM / anti-bot.

### D86 — Distilled prompts are reverse-inferred guidance, gated, and never auto-adopted
A `PromptBlueprint` is "what our agent needs to reproduce the good features",
not the creator's original prompt; long verbatim source text is never copied in.
One reference → `OBSERVED`/`EXPERIMENTAL` only (single-source guard).
`AUTO_PROMOTE_LEARNED_PROMPTS` is false — a human or a VALIDATED experiment
promotes; `PromptComposer` in production injects only `PROMOTED` blueprints and
labels the block advisory / subordinate to facts + policy + copyright. Every
blueprint keeps traceable `PromptBlueprintEvidence` (external ref id or internal
campaign + metric_delta). Internal Analytics evidence outranks external references.

### D87 — Platform selection: check-off skips GENERATION, not just publishing
`campaign_platform_selections` holds a 3-state mode per platform/content-type
(`DISABLED` / `GENERATE_ONLY` / `GENERATE_AND_PUBLISH`). `set_selection` writes
`Campaign.platforms` = the non-DISABLED set, which is the only list the media
pipeline builds — a DISABLED platform produces no content, media, thumbnails,
jobs or API calls. `create_jobs_for_campaign` makes a job only for
GENERATE_AND_PUBLISH; the Publisher re-reads the selection right before the remote
call and blocks a platform deselected after the job was queued
(`PLATFORM_DESELECTED`, fail-closed). A user-explicit selection locks the campaign
(`platform_selection_locked`) and Autopilot cannot re-enable a platform the user
turned off. Cost preview is `PRICING_UNKNOWN` while media providers are MOCK — no
fabricated dollar figures.

### D88 — Generated output is similarity-checked against learned references
`intel/reference_guard.check_against_references` compares generated Hook / Title /
Script against the campaign's learned reference chunks
(`reference_similarity_fix_threshold`, default 0.82, reusing the Phase 7
`text_similarity`) and routes a near-copy to governance `FIX_REQUIRED`. A campaign
with no learned references is a no-op, so pre-upgrade content is unaffected.

### D89 — Ollama is a first-class LLM provider over stdlib HTTP; the app never depends on it
`app/providers/ollama_llm.OllamaLLMProvider` implements the same `.complete`
contract as the cloud adapters, talking to the Ollama REST API via stdlib
`urllib` — **no `ollama` python package** (spec §14). `health()` never raises;
`complete()` raises a normalized `ProviderError`. Ollama being down returns HTTP
200 `status: NOT_RUNNING` and marks local models `DOWN` — it never crashes the
app. Verified locally: Ollama 0.33.2 + `gemma3:4b` reachable, JSON inference
round-trips → LOCAL_VERIFIED (`tests/ai_router/test_ollama.py`). Config:
`OLLAMA_ENABLED` / `OLLAMA_BASE_URL` / `OLLAMA_DEFAULT_MODEL` /
`ALLOW_CLOUD_FALLBACK`. Models (GB) are never auto-pulled.

### D90 — Model Router picks the engine by task fit, not price; deterministic tasks use no model
`app/ai_router/` — tiers `deterministic` (Python, no model) / `local_light`
(Ollama first) / `standard` (local or cheap cloud) / `premium` (premium cloud,
then cheaper, then local). Selection weighs task fit + quality + cost + latency +
reliability + privacy. `ALLOW_CLOUD_FALLBACK=false` (**LOCAL_ONLY**) removes every
cloud model from consideration and a task fails clearly rather than silently
calling a cloud model. `run_routed` escalates on schema-invalid / low-confidence
and walks a bounded (≤4) fallback chain. `hash`/`classification` never reach a
premium model, even at `QUALITY_PRESET=max`. Migration `0010_phase8`
(`model_routing_events`, `model_performance`). Routing memory (`ModelPerformance`)
stays `UNKNOWN` until `MODEL_ROUTING_MIN_SAMPLE` (8) observations — no policy flip
on n=1.

### D91 — Cost is estimated before a run, with explicit KNOWN / ESTIMATED / UNKNOWN state
`app/ai_router/cost.estimate_campaign_cost` — per-category (LLM / learning /
Search / Image / Video / TTS / Stock / Storage). Media providers are MOCK, so
those lines are `UNKNOWN` — **never a fabricated number**. Local (Ollama) API
cost is a real `0` shown as "LOCAL PROCESSING · API ₩0", never "무료". Shared
master assets are counted once; only per-platform adaptation scales with the SNS
selection; a DISABLED platform adds zero platform-specific cost; the estimate
recomputes on every selection change. Cheap-first learning (Stage 1 deterministic
→ Stage 2 local → Stage 4 deep on top-K only) was already in place from the
Intelligence Upgrade.

### D92 — Content Library is a read model over EVERY existing content, legacy included
`app/library/` aggregates `Campaign` / `PlatformContent` / `Asset` / `Script` /
`Publication` / `AnalyticsSnapshot` / `RevenueEntry` / `CostLog` (+ references /
governance when present) — **no new content table, nothing deleted or
regenerated**. Pre-Phase-6/7/8 campaigns (`workspace_id IS NULL` and no
`execution_mode`) get a `LEGACY` badge and render without error (governance
`NOT_APPLICABLE`, missing metrics `—`). Real MP4s stream via
`GET /api/library/{id}/media/video`; `advanced_short`/`sample`/`demo` renders are
flagged `is_demo`, never shown as production. `add-platform` adds one platform to
an existing campaign (media pipeline builds only that platform; existing ones
never regenerate; already-selected → 409). Server-paginated
(`content_library_page_size`).

### D93 — Phase 8 UX is beginner-first and additive; no framework change, minimal deps
Next.js/TS/Tailwind unchanged. New routes: `/create`, `/library` +
`/library/[id]`, `/setup` (8-step, `localStorage`-resumable), `/settings/local-ai`,
`/calendar`, `/system`. Existing pages reused. Korean-first labels; internal
enums only in Expert detail. Status conveyed by text as well as colour.
`localStorage` used only for the setup-wizard draft. `.env.example` added;
`scripts/start-local.ps1` / `stop-local.ps1` added (never reset the DB). **0 new
runtime dependencies** (Playwright browser-E2E remains OPTIONAL / not wired).

### D94 — Every production agent LLM call goes through the Model Execution Gateway (AUDIT-P8-001 repair)
`app/agents/model_gateway.py::routed_complete(...)` is the single door for
research / fact_check / strategy / hook / script / script_qa (via
`nodes.py::_run_llm`) and platform_adapt / scene_plan / edit_decision (via
`media_nodes.py::_llm_json`), plus the natural-writing rewrite (`GatewayLLM`
shim). It maps the agent task to a router `(agent_type, task_type)`, runs
`ai_router.run_routed` (select → provider → structured-output validation → bounded
escalation on schema-invalid/low-confidence → fallback chain → routing telemetry +
cost), passes the **original** task label as `provider_task` (so the provider /
mock keys off it), threads `campaign_id`/`workspace_id`, and on any router error
falls back to `get_llm_provider().complete()` — the **only** sanctioned direct
provider call outside the router/benchmark/health paths. `get_llm_provider`
imports were removed from both agent modules; a static test
(`tests/agents/test_model_gateway.py`) fails if a direct provider call/import
reappears. Support: a MOCK-MODE `mock` registry entry (+ `_provider_for("mock")`)
keeps a routed decision + telemetry flowing in dev/test without a key;
`RoutedResult` carries token counts. **No schema change, no new dependency.**
Evidence: a light agent task routes to `gemma3:4b`; a full campaign emits ≥4
`ModelRoutingEvent` rows across `standard` + `premium`; LOCAL_ONLY + local failure
→ 0 cloud calls. AUDIT-P8-001 → RESOLVED; master-audit verdict C → **B**.
Not covered (tracked as AUDIT-P8-006): the gateway does not yet merge
`intel.composer.compose(...)` (learned skills / blueprints) into the system prompt.

### D95 — Phase 1–8 baseline hardening: all 7 MEDIUM gaps resolved, baseline LOCKED (MASTER MEDIUM GAP REPAIR)
- **AUDIT-P8-006** — `model_gateway._compose_system()` calls `intel.composer.compose(...)`
  BEFORE `run_routed`, merging Base + Brand + Channel + Memory + agent-alias /
  platform / brand-filtered Learned Skills + Prompt Blueprints under
  `max_learned_context_tokens`. Retrieval is deterministic DB reads (cheap-first —
  no extra LLM). Strict production default (PROMOTED blueprints only) and the user
  disable switch (`ReferenceFeedback` verdict BLOCK/NOT_USEFUL/WRONG, new
  `composer.disabled_ids`) are honoured. Lineage — `prompt_composer_used`,
  `skill_ids`, `blueprint_ids`, `memory_ids`, `prompt_version`, `context_tokens`,
  `truncated` — rides `GatewayResponse` and is persisted to
  `ModelRoutingEvent.prompt_lineage` (migration `0011_medium_repair`, additive
  nullable JSON — the only schema change). Master switch
  `config.prompt_composer_enabled` (default true). AUDIT-P8-001 flow unchanged;
  the direct-provider bypass guard still asserts 0.
- **AUDIT-P8-005** — `ModelRouter._apply_performance(db, task_type, cands)` reorders
  candidates by learned `ModelPerformance` strength (STRONG first, WEAK last,
  unmeasured neutral) when a `db` is threaded from `run_routed` and
  `model_routing_autotune_enabled` (default true). No shift below
  `model_routing_min_sample` — `performance_hint` already excludes UNKNOWN.
- **AUDIT-P8-003** — `app/library/search.py::global_search` + `GET /api/search`
  across Campaign (topic + Script body) / PlatformContent / Channel / Brand /
  ReferenceSource / Publication; deterministic exact>prefix>word>substring score;
  workspace-scoped; `kinds` filter; capped set.
- **AUDIT-P8-002** — `app/edit/nl_to_request.py`: deterministic KR/EN phrase table
  → typed `EditRequest`; pure `apply_edit`; `impact_of` wraps the existing
  Smart-Rerender planner into a human "re-runs X" preview. `POST
  /api/library/{id}/edit-plan` previews without rendering. Scene-editor *panel* UI
  deferred to LOW (AUDIT-L-003).
- **AUDIT-P8-004** — `frontend/lib/api.ts::finishSetup` + `app/setup/page.tsx`
  "설정 완료" POST `/api/workspaces` then `/api/brands` (reuse-by-name, safe re-run).
  `create_workspace` / `create_brand` now `db.commit()` — they previously only
  `flush()`ed, so the wizard's writes were silently discarded.
- **AUDIT-P6-001** — `app/autopilot/capacity.py`: deterministic per-channel
  `remaining_slots` + `budget_headroom` from today's Campaigns / PublishJobs /
  CostLog / Asset cost; `portfolio_capacity → max_new_campaigns`. Autopilot
  controller caps its selection by it (`autopilot_respect_channel_capacity`,
  default true; falls back to `autopilot_daily_content_max` with no channels —
  single-stream autopilot unchanged). `GET /api/publishing/calendar/capacity`.
- **AUDIT-P7-001** — `app/governance/policy_verify.py`: `verification_report`
  (stale/UNKNOWN review queue, each `LEGAL_REVIEW_REQUIRED`), attributed
  `record_verification` (bumps `last_verified_at`, `UNKNOWN→ACTIVE` only on
  explicit `activate_unknown`, writes a `GovernanceEvent`), `due_for_review`. No
  live fetch — stays NEEDS_PRODUCTION_ENVIRONMENT. `GET /api/policy/verification`,
  `POST /api/policy/verify`.
- **1 additive migration** (`0011_medium_repair`), **0 new dependencies**. New
  targeted tests: +37 (P8-006 11, P8-005 3, P8-003 5, P8-002 5, P6-001 5,
  P7-001 6, P8-004 2). Master-audit verdict stays **B**; **can proceed to Phase 9: YES**.

### D96 — Phase 9 Real-World Validation: local/staging validation complete, production verification pending
New suite `tests/phase9/` (59 tests: smoke / load / failure / recovery / security /
soak / e2e-journeys) exercises concurrency, time, and fault injection against the
Phase 1–8 baseline. **Full regression 545 passed / 0 failed** (486 baseline + 59).
- **Load**: 20 concurrent Phase 1-A pipelines — 0 corruption, DB pool bounded
  (high-water 11 checked-out / 8 overflow, no exhaustion). LEARN_ONLY batch 100 →
  0 production rows, deep analysis capped at `learning_deep_analysis_top_k` (20),
  0 premium LLM calls.
- **Failure/recovery** (via `app.providers.faults`): LLM TIMEOUT/RATE_LIMIT retry,
  AUTH_ERROR non-retryable + surfaced (no fake success), search failure →
  INSUFFICIENT_RESEARCH, DB `engine.dispose()` → `pool_pre_ping` reconnect,
  transaction rollback → no orphan, Redis DOWN → graceful, **restart-resume → 0
  duplicate AgentRuns**, cancel → 0 new work.
- **Publishing**: concurrent double-fire of one PublishJob → 1 remote post
  (idempotency_key + remote_post_id); retry → `idempotent_skip`; expired
  `RightsLedger` + scheduled publish → worker re-check blocks, 0 remote.
- **Security at batch scale**: 1 poisoned reference among 12 → 0 execution;
  SSRF (localhost/169.254.169.254/file://) + redirect-to-private blocked
  end-to-end through the learning engine; the app's own `localhost:11434` Ollama
  path is unaffected by the user-fetch SSRF guard.
- **All 12 Phase 1–8 invariants re-verified** as a block
  (`test_invariant_recheck.py`): LEARN_ONLY=0 production, SNS-OFF=0 gen/publish,
  LOCAL_ONLY=0 cloud, Governance BLOCK=0 publish, Viewer write forbidden, tenant
  isolation, queue-off race, single-scene repair scoped, budget hard limit,
  direct-provider bypass=0, PromptComposer on the agent flow.
- **QUICK_SOAK** 180 s / 123 cycles: Python heap flat (+0.0008 MB/sample), DB pool
  flat at 0, 0 failed. No leak. (FULL_SOAK = AVAILABLE_NOT_REQUIRED.)
- **Defect P9-001 (MEDIUM, FIXED)**: `library.service.list_content` enriched every
  matching campaign before pagination — 9.3 s at 1000 campaigns. Fixed with a
  DB-level `OFFSET/LIMIT` fast path (`_card()` helper); full-scan retained only
  for python-only filters (`platform`/`content_type`/`governance`/`publish_state`)
  and metric sorts. **0.25 s, flat across pages.**
- Browser E2E: no JS runner installed; Playwright is a new dev dep needing D67
  approval + global install is disallowed → HTTP-level journey tests +
  `tsc --noEmit` + `next build` (both clean) stand in. Rendered-browser E2E is
  AVAILABLE_NOT_REQUIRED for this gate.
- **0 new dependencies. 0 new migrations** (Phase 9 is a validation phase; the
  only code change is the P9-001 fix in `app/library/service.py`).
- Docs: `PHASE9_REAL_WORLD_VALIDATION.md`, `LOAD_TESTING.md`, `STRESS_TESTING.md`,
  `SOAK_TESTING.md`, `FAILURE_RECOVERY.md`, `CHAOS_TESTING.md`, `BROWSER_E2E.md`,
  `PERFORMANCE_BASELINE.md`, `OPERATIONS_RUNBOOK.md`.
- **Verdict: B — PHASE 9 LOCAL/STAGING VALIDATION COMPLETE, PRODUCTION
  VERIFICATION PENDING.** Can proceed to Phase 10: YES (not started — awaiting
  approval). Production-pending items unchanged (credentials / environment).

### D97 — Production V1.0 (Phase 10): release engineering + kill switches + AI Support Snapshot + responsive dashboard
- **Version `1.0.0`** (`config.app_version` + `release_name`; `GET /api/support/version`;
  FastAPI OpenAPI; `/support` page; AI Support Snapshot). Was `0.5.0-phase5`.
- **Production kill switches** — extended `app/ops/runtime_flags.py` with
  `GLOBAL_PUBLISH_PAUSE` + `GLOBAL_PAID_PROVIDER_PAUSE` (DB-backed via
  `RuntimeSetting`, survive restart, 3 s cache). Wired to real gates:
  `publishing/engine.py::run_publish_job` short-circuits before any remote work
  (job stays `READY`, not failed) on `publish_paused()` or `emergency_stop_active()`;
  `ai_router/execute.py::_provider_for` raises on `paid_provider_paused()` for the
  `anthropic` provider only — local Ollama + mock still returned. `POST
  /api/ops/flags/<FLAG>` now accepts the two new flags (confirm required to enable).
- **AI Support Snapshot** — new `app/support/` (`snapshot.py` aggregation,
  `errors.py` code normaliser + Korean suggested actions) + `app/api/routes_support.py`
  (`GET /api/support/snapshot`, `/snapshot.txt`, `/version`). Read-only,
  every field from a real source (DB / health / queue / worker / routing
  telemetry / governance / cost). **Secret-redacted** — whole payload through
  `app/ops/redaction.py`; that util's value patterns were hardened
  (`sk-(ant-)?…`, `sk_(live|test)_…`, `gh[pousr]_…`). **RBAC-scoped** — a normal
  user sees only their workspace (`ctx.assert_workspace` IDOR guard); a system
  admin gets infra detail; 0 other-tenant data; the test block is admin/non-prod
  only. Frontend `/support` page: responsive, **capture mode** (`body.capture-mode`
  hides `[data-chrome]` + `.capture-hide`), **[지원 정보 복사]** → `snapshot.txt`
  to clipboard. `tests/phase10/test_support_snapshot.py` (13): shape, real data,
  secret redaction (planted keys/tokens/DSN never leak), tenant scope, error-code
  normalisation + suggested action per failure mode, admin-vs-user detail,
  screenshot-sized text.
- **Production config validator** — `app/ops/config_check.py` + `GET
  /api/ops/config-check`; per-capability status
  (`READY/DEGRADED/NOT_CONFIGURED/NEEDS_CREDENTIALS/NEEDS_PRODUCTION_ENVIRONMENT/
  MISCONFIGURED`); flags `silent_mock_fallback_in_prod`; delegates hard prod
  checks to the existing `app/ops/env.py::validate_environment`.
- **Responsive dashboard** — `components/AppShell.tsx`: sticky top bar (name +
  `v1.0` + persistent "AI 지원"), grouped desktop nav (`hidden md:flex`), 5-slot
  mobile bottom nav + "더보기" bottom sheet. Design tokens in `tailwind.config.ts`
  (one accent `#4f46e5`, semantic status colours, `card`) + `globals.css`
  `@layer components` (`.card` / `.btn-*` / `.chip` / `.kv`). **No template was
  cloned; 0 npm dependencies added** — patterns only, from Kiranism /
  satnaing / reoring / TailAdmin / Tremor-OSS (all MIT/Apache-2.0);
  `docs/DASHBOARD_REFERENCE_AUDIT.md`, `OPEN_SOURCE_COMPONENTS.md`.
- **0 new backend/frontend dependencies. 0 new migrations** (head stays
  `0011_medium_repair`). Frontend `tsc --noEmit` + `next build` clean. Secret
  scan clean.
- **Verdict: B — V1.0 RELEASE CANDIDATE READY; REAL CREDENTIAL / INFRA
  VERIFICATION PENDING.** Controlled production pilot (1×1, human-approved): YES.
  Unrestricted full automation: NO. Docs: `RELEASE_V1.md`,
  `PRODUCTION_DEPLOYMENT.md`, `PRODUCTION_CHECKLIST.md`,
  `PRODUCTION_CONFIGURATION.md`, `PROVIDER_SETUP.md`, `SNS_SETUP.md`,
  `PLATFORM_SUPPORT_MATRIX.md`, `BACKUP_AND_RECOVERY.md`,
  `MONITORING_AND_ALERTS.md`, `INCIDENT_RESPONSE.md`, `SECURITY_CHECKLIST.md`,
  `KNOWN_LIMITATIONS.md`, `AI_SUPPORT_SNAPSHOT.md`, `DESKTOP_DASHBOARD.md`,
  `MOBILE_DASHBOARD.md`, `DASHBOARD_REFERENCE_AUDIT.md`, `OPERATIONS_RUNBOOK.md`
  (updated), `OPEN_SOURCE_COMPONENTS.md` (updated).

### D98 — Google AI (Imagen/Veo) + ElevenLabs providers connected (Phase 11)
Integrated into the **existing** media provider abstraction — no new framework,
**0 new dependencies** (stdlib `urllib`, same as `OllamaLLMProvider`), **0 new
migrations**.
- **Config** (`app/config.py`): canonical `GOOGLE_API_KEY` / `ELEVENLABS_API_KEY`
  (+ fallback to the existing `image_api_key`/`video_api_key`/`tts_api_key`).
  Reuses the existing `image_provider` / `video_provider` / `tts_provider`
  convention (`mock | google` / `mock | elevenlabs`). Model names live ONLY here
  (`google_image_model=imagen-3.0-generate-002`, `google_video_model=veo-3.0-generate-001`,
  `elevenlabs_model=eleven_multilingual_v2`) — never hardcoded in adapters.
  `Settings.media_provider_key(kind)` resolves the per-vendor key;
  `media_provider_is_mock()` updated to use it.
- **Adapters** (`app/providers/media/`): `_http.py` (shared stdlib JSON/bytes +
  `provider_error(vendor, kind, msg)` → `ProviderError` with a standard
  `error_type` AND a `provider_code` like `GOOGLE_AUTH_FAILED`);
  `google_image.py` (`GoogleImageProvider` — Imagen `:predict`, aspect-ratio
  mapping, base64→file, `cost=0.0` + `meta.cost_state="UNKNOWN"`, read-only
  `health()` via `GET /v1beta/models`); `google_video.py` (`GoogleVideoProvider`
  — Veo `:predictLongRunning` → **bounded synchronous poll** of the operation →
  retrieve; fits the sync `VideoProvider` protocol so the worker/checkpointer/
  idempotency model is untouched; `_existing_scene_asset` reuse still prevents
  re-generation on restart); `elevenlabs_tts.py` (`ElevenLabsTTSProvider` —
  `/with-timestamps` + `pcm_24000` wrapped in a 24 kHz WAV so the timing/subtitle/
  render pipeline is unchanged; duration from alignment; `ELEVENLABS_VOICE_ID`
  required, no invented default; no voice cloning).
- **Registry** (`registry.py`): `get_image_provider()` / `get_video_provider()` /
  `get_tts_provider()` return the real adapter only when
  `<kind>_provider == google|elevenlabs` AND a key is present AND `mock_mode` is
  off AND `GLOBAL_PAID_PROVIDER_PAUSE` (Phase 10 kill switch) is not active —
  otherwise the existing mock/None. `get_video_provider()` no longer always
  returns `None`. **The `gen_images_node` render loop still downgrades AI_VIDEO to
  image-motion** (`max_ai_video_ratio` default 0) — the Veo adapter is connected
  at the abstraction/registry level; invoking it from the render pipeline is a
  deliberate opt-in (raise `MAX_AI_VIDEO_RATIO` + add the media-node call site).
- **Status / observability**: `app/providers/status.py` +
  `GET /api/providers` (anthropic / tavily / google / elevenlabs / ollama →
  `CONNECTED / NOT_CONFIGURED / DEGRADED / ERROR`; cached read-only probes; **no
  key value ever returned**). AI Support Snapshot `system.cloud_providers` now
  carries `google_key_present` / `elevenlabs_key_present` + the `providers` array;
  `/support` page lists each. `app/support/errors.py` maps the new
  `GOOGLE_*` / `ELEVENLABS_*` codes to Korean suggested actions;
  `RATE_LIMITED` codes are retryable. `app/ops/config_check.py` adds `GOOGLE_AI`
  / `ELEVENLABS` / refined `MEDIA_PROVIDERS` capability rows.
- **`.env.example`** rewritten: `LLM_PROVIDER=anthropic`, `SEARCH_PROVIDER=tavily`,
  `GOOGLE_API_KEY` + `IMAGE_PROVIDER`/`VIDEO_PROVIDER` + models, `ELEVENLABS_API_KEY`
  + `TTS_PROVIDER` + `ELEVENLABS_VOICE_ID` + model, Ollama block.
- **Tests** `tests/phase11/` = 32 (google 16, elevenlabs 7, status/snapshot/
  invariants 9) — all HTTP mocked, **no paid call**. Invariants re-checked:
  direct-provider bypass = 0, existing Anthropic/Tavily/Ollama selection
  unchanged, `GLOBAL_PAID_PROVIDER_PAUSE` falls media back to mock, LEARN_ONLY
  still generates 0 media. Affected regression (phase10/media/pipeline/ai_router/
  ops/agents/intel) = 262 passed / 0 failed. Frontend `tsc` + `next build` clean,
  secret scan clean.
- **Anthropic stays the primary cloud LLM** — not replaced.
