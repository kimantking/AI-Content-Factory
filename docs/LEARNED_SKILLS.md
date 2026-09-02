# LEARNED SKILLS & CREATIVE RECIPES

> Code: `backend/app/intel/skills.py`. Tables: `learned_skill_notes`,
> `creative_recipes`.

## LearnedSkillNote

A small, testable rule for one agent — not just a prompt string:
`agent_type`, `skill_category`, `rule`, `rationale`, `evidence_ids`, `confidence`,
`sample_size`, `platform`, `content_type`, `topic_cluster`, `status`, `version`.

Example:
> **B-roll Director** · `visual_evidence` — "숫자 Claim에는 generic B-roll보다
> 증거성 Visual(차트/문서)을 우선한다." · sample_size 27 · confidence 0.86

`derive_skill_notes()` maps an analysis kind to a rule template
(`_SKILL_RULES`): B-roll / graphics / audio / hook / cut rhythm / caption /
pacing / story / writing / retention / facts / knowledge / technical-rights /
positioning. `status` = `OBSERVED` (1 ref) → `EXPERIMENTAL` (<3) → `CANDIDATE`
(≥3). The rule text is a fixed abstraction — reference source text is never
embedded.

## CreativeRecipe (spec §AC)

Combine the best sub-profile from several references: Hook from video A, Story
from B, Subtitle from C, Audio from D. `compose_creative_recipe(picks=…)` where
each `picks[key]` may carry `_ref` (its source reference id). `evidence_ids` is
the union of contributing references; `confidence` grows with the number of
filled sub-profiles + distinct sources.

## Retrieval

The PromptComposer (`PROMPT_DISTILLATION.md`) pulls the top `max_learned_skills`
notes for the requesting agent, filtered by platform / content-type /
topic-cluster, and only `EXPERIMENTAL`+ status. Notes stay advisory — they never
override facts, platform policy, or copyright/governance rules, and the composer
says so in the injected section header.

## Skill gap detector (`intel/gap.py`)

Reads recent `PerformanceScore.components` for weak dimensions (mean < 0.45) and
maps them to the dataset type to grow (`retention → VIDEO_DATASET`,
`thumbnail_ctr → THUMBNAIL_DATASET`, `voice_naturalness → VOICE_DATASET`, …),
plus flags any dataset type below its target count. Surfaced on the Learning
Studio dashboard as "더 배우면 좋은 데이터".
