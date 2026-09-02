# UI ARCHITECTURE — Phase 8

> Next.js (app router) + TypeScript + Tailwind. Stack unchanged (spec §70).
> API client: `frontend/lib/api.ts`.

## UI modes (spec §5)

`BEGINNER` (default) / `STANDARD` / `EXPERT`. Beginner hides internal concepts
(Agent, LangGraph, Queue, Prompt Registry, Provider internals, Rights Ledger,
Dataset internals). Expert screens (Prompt Lab, model registry, raw JSON tabs)
expose the enum-level detail. Korean-first labels; internal enums appear only in
Expert / technical detail (spec §73).

## Navigation (spec §6)

Main: 만들기 (`/create`) · 콘텐츠 (`/library`) · 캘린더 (`/calendar`) · AI 학습실
(`/learn-studio`) · 채널 (`/portfolio`) · 분석 (`/analytics`) · 오토파일럿
(`/autopilot`) · 검수 (`/governance`) · 자료실 (`/references`).
Advanced: 설정 (`/setup`) · 로컬 AI (`/settings/local-ai`) · 계정 (`/publishing`) ·
Prompt Lab (`/prompt-lab`) · 시스템 (`/admin`) · 상태 (`/system`).

## Routes added in Phase 8

`/create` (Quick Create + cost preview + local-AI awareness), `/library` +
`/library/[id]` (Content Library + detail with video preview), `/setup` (8-step
resumable wizard), `/settings/local-ai` (Ollama status + model registry +
per-task performance), `/calendar` (month view of scheduled publishes), `/system`
(plain-language system status). Existing pages (`/governance`, `/publishing`,
`/portfolio`, `/analytics`, `/autopilot`, `/learn-studio`, `/references`,
`/prompt-lab`, `/compose`, `/admin`) are reused.

## Performance (spec §74)

Content / references / campaigns lists are server-paginated; the client never
receives the full set. `content_library_page_size` default 30.

## Accessibility (spec §72)

Semantic `<button>` / `<a>`, form `<label>`s, keyboard-usable controls, visible
focus, and **status conveyed by text as well as colour** (e.g. "정상 / 문제 /
확인 불가", "PUBLISHED / SCHEDULED / BLOCKED" beside the dot).

## Design

Modern SaaS-dashboard styling (rounded cards, subtle borders, muted palette) —
not a bare admin screen. Desktop-first; core flows work on tablet/mobile via
`flex-wrap` / responsive grids.

## Verification

`tsc --noEmit` clean; `next build` clean. Browser E2E (Playwright) is OPTIONAL /
not wired (no new dependency); flows are covered by backend API tests +
`tests/test_phase8_e2e.py`.
