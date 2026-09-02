# LEARNING STUDIO

> UI: `frontend/app/learn-studio` (`/learn-studio`, nav "학습실"),
> `frontend/app/references` (Reference Library), `frontend/app/prompt-lab`.
> API: `backend/app/api/routes_intel.py`. Engine: `URL_LEARNING_ENGINE.md`.

## Purpose

A place to feed reference URLs and *learn only* — no campaign, no media, no
publish. Default `execution_mode` here is **LEARN_ONLY**. The one-screen campaign
creator (`/compose`) uses **CREATE_AND_LEARN**.

## Screens

- **AI 학습실 (`/learn-studio`)** — paste URLs, pick learning purpose (`AUTO` /
  `FACT_SOURCE` / `KNOWLEDGE` / `STYLE_REFERENCE` / `VIDEO_REFERENCE` /
  `COMPETITOR_REFERENCE` / `TECHNICAL_REFERENCE`) and scope (`THIS_RUN` /
  `THIS_CAMPAIGN` / `CHANNEL` / `BRAND` / `WORKSPACE`), run a LEARN_ONLY job.
  Shows the Learning Dashboard + "더 배우면 좋은 데이터" (SkillGapDetector).
- **Reference Library (`/references`)** — every reference with status / quality /
  weight / rights / injection flag; click a row for the extracted analyses.
- **Prompt Lab (`/prompt-lab`)** — Learned Skills + Prompt Blueprints with
  Preview/Test (PromptComposer preview), status advance (OBSERVED → EXPERIMENTAL →
  CANDIDATE → VALIDATED → PROMOTED) and Rollback. Evidence for each blueprint is
  listed and every row is reference-traceable.

## Dashboard fields (`GET /api/learning`)

Total / Ready References, Dataset Records, Video References, Writing References,
Prompt Blueprints, Learned Skills, Creative Recipes, Collections, Learning Cost,
Last Learning Run.

## Compose screen (`/compose`, `POST /api/campaigns/compose`)

One screen: topic + reference URLs + execution mode + per-platform / per-content-type
3-state selection (`DISABLED` / `GENERATE_ONLY` / `GENERATE_AND_PUBLISH`) + presets
+ 전체 선택 / 전체 해제 + a cost preview. On submit it creates the campaign (unless
LEARN_ONLY), stores the platform selection, runs the reference-learning job, and
enqueues the pipeline for the selected platforms only.

## API surface

`/references`, `/references/analyze`, `/references/{id}`, `/learning`,
`/learning/jobs[/{id}]`, `/learning/collections`, `/learning/datasets`,
`/learning/skills`, `/learning/prompts[/{id}]`, `/learning/prompts/{id}/test`,
`/learning/prompts/{id}/promote`, `/learning/prompts/{id}/rollback`,
`/learning/recipes`, `/learning/gaps`, `/platform-selection[/{campaign_id}]`,
`/platform-selection/content-types`, `/platform-presets`, `/campaigns/compose`.

## Watchlist (spec §AN) — opt-in only

`LearningCollection.watchlist` can hold user-registered RSS / official feed / API
sources. New references there create a LEARN_ONLY job. There is **no** unbounded
crawling.
