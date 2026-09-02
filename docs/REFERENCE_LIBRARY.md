# REFERENCE LIBRARY

> Code: `backend/app/db/models_learn.py` (`reference_sources`, `reference_chunks`,
> `reference_analysis`, `learning_collections`, `reference_feedback`).
> UI: `frontend/app/references`.

## ReferenceSource

One row per learned URL: `url` / `canonical_url` / `url_hash`, `source_type` +
`support_level`, `purpose` + `resolved_purpose` (AUTO → concrete via
`router.resolve_purpose`), `scope` (`THIS_RUN` … `WORKSPACE`), `status`
(`PENDING` → `FETCHING` → `EXTRACTED` / `LOW_VALUE` / `DUPLICATE` / `BLOCKED` /
`FETCH_FAILED` → `READY` / `REMOVED`), extracted metadata (title / author /
publisher / dates / language), `content_hash` + `text_fingerprint`, the quality
component scores + `learning_weight`, `rights_status` (default
`RESEARCH_REFERENCE`), `injection_flag` + `injection_detail`, `topic_cluster`,
`tags`, `cost_usd`, and tenant scope (`workspace_id` / `brand_id` / `channel_id`).

## ReferenceAnalysis

One row per `(reference_id, analysis_kind)` — the extracted structure lives in
`data` (JSON) with `confidence` and `unknown_fields`. Kinds: `QUALITY`, `FACTS`,
`KNOWLEDGE`, `WRITING_PROFILE`, `VIDEO_OBSERVATION`, `HOOK_PATTERN`,
`STORY_PROFILE`, `EDITING_PROFILE`, `BROLL_PROFILE`, `SUBTITLE_PROFILE`,
`VOICE_PROFILE`, `AUDIO_PROFILE`, `GRAPHICS_PROFILE`, `THUMBNAIL_PROFILE`,
`RETENTION_PATTERN`, `GITHUB_ANALYSIS`, `COMPETITOR_ANALYSIS`. This one table
replaces a dozen near-duplicate profile tables (spec "중복 Table 금지").

## Collections (spec §AI)

`LearningCollection` — a user-named bucket ("잘 만든 AI 쇼츠", "좋은 자막",
"GitHub Agent 기술", …) with a `default_purpose` / `default_scope` and an opt-in
`watchlist` (RSS / feed / API sources only — no crawling).

## Video deep analysis (spec §M-§R)

`VideoReferenceAnalyzer` works from a **caller-supplied structured profile** (a
YouTube-API field set, a user's edit list, scene timings) — never frame-level CV.
`video_observation()` returns every field from `_VIDEO_FIELDS`, marking anything
not present as `UNKNOWN` and reporting `_coverage`. `video_subprofiles()` splits
it into Hook / Story / Editing / B-roll / Subtitle / Voice / Audio / Graphics /
Thumbnail / Retention profiles. **No fabricated analysis numbers.** Real frame CV
is an OPTIONAL adapter, not built.

## Feedback & removal

`ReferenceFeedback` records per-reference / per-blueprint / per-skill verdicts
(`USEFUL` / `NOT_USEFUL` / `WRONG` / `BLOCK`). Removing a reference (status
`REMOVED`) cascades to its chunks/analyses; blueprint & skill confidence should be
recomputed from remaining evidence (`DataCurator` + recompute on next run).
