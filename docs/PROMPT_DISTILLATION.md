# PROMPT DISTILLATION ENGINE

> Code: `backend/app/intel/distillation.py`, `intel/composer.py`. Tables:
> `prompt_blueprints`, `prompt_blueprint_evidence`.

## What it does — and does NOT

It does **not** claim to recover a creator's original prompt. It reverse-infers:
"what production instructions would OUR agent need to reproduce the good,
verifiable features of this result?" — a **PromptBlueprint** (instructions,
constraints, positive/negative patterns, target platforms/content-types).

Long verbatim source text and unusual phrasings are **never** copied into a
blueprint or a skill note — only abstracted, high-level guidance.

## Guards

- **Single-source guard** — one reference can only reach `OBSERVED` /
  `EXPERIMENTAL` (`learning_single_source_max_status`), never `PROMOTED`.
  `advance_status` refuses to move a `sample_size ≤ 1` blueprint past
  `EXPERIMENTAL`.
- **Multi-reference confidence** — `confidence = 0.35·min(n/10,1) +
  0.25·source_diversity + 0.20·quality + 0.20·consistency`. `sample_size <
  learning_min_blueprint_sample` (3) caps status at `EXPERIMENTAL`.
- **`AUTO_PROMOTE_LEARNED_PROMPTS` is false** — `advance_status(..., "PROMOTED")`
  by `actor="system"` is refused unless the reason is `EXPERIMENT_VALIDATED…`.
  A human, or a VALIDATED experiment, promotes.
- **Evidence is always traceable** — every blueprint has
  `PromptBlueprintEvidence` rows (`EXTERNAL_REFERENCE` with `reference_id`, or
  `INTERNAL_CONTENT` with `campaign_id` + `metric_delta`).

## Status state machine

`OBSERVED → EXPERIMENTAL → CANDIDATE → VALIDATED → PROMOTED`; `→ DEPRECATED`
and `→ REJECTED` from most states; `rollback` sends `PROMOTED → VALIDATED`
(otherwise `→ DEPRECATED`). Invalid transitions are rejected.

## Internal data outranks external (spec §Y)

`distillation.add_internal_evidence(blueprint_id, campaign_id, metric_delta, …)`
wires a Phase 3 Analytics result to a blueprint as `INTERNAL_CONTENT` evidence
(weight 1.5) and bumps `sample_size` + `confidence`.

## PromptComposer (`intel/composer.py`)

`compose(agent_type, base_prompt, …)` assembles: **BASE + BRAND + CHANNEL +
MEMORY + LEARNED_GUIDANCE** where LEARNED_GUIDANCE is the top relevant Learned
Skills + Prompt Blueprints under `max_learned_context_tokens` (truncates,
reports `truncated`). Caps: `max_learned_skills` (8), `max_prompt_blueprints` (5).

- **Agent-specific retrieval** — a Hook Agent gets hook patterns; a Subtitle
  Director gets subtitle profiles (`_AGENT_ALIASES`).
- **Platform-specific retrieval** — a `tiktok`-tagged blueprint is not applied to
  a `youtube_long` request.
- **Production strictness** — with `auto_promote_learned_prompts` false and
  `include_experimental=False`, only `PROMOTED` blueprints are injected. The
  Prompt Lab preview passes `include_experimental=True`.

## Self-improvement loop (spec §Z)

Reference → feature extraction → dataset → pattern → PromptBlueprint → experiment
→ our content → Analytics → learning → confidence update → promotion / deprecation
recommendation. Automatic up to blueprint generation + confidence update;
**production adoption needs a human or a VALIDATED experiment**.
