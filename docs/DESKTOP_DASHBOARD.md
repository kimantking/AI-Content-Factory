# Desktop Dashboard (Phase 10)

The desktop view is the full **production control center**. One Next.js codebase;
desktop / tablet / mobile differ only in layout and information priority
(`components/AppShell.tsx`, `tailwind.config.ts` tokens, `globals.css` `@layer
components`). No separate codebase, no template transplant (see
`DASHBOARD_REFERENCE_AUDIT.md`).

## Shell
* Sticky top bar: product name · `v1.0` chip · **AI 지원** link (always reachable).
* Grouped nav (`hidden md:flex`): 홈 · 콘텐츠 · 캘린더 · AI 학습실 · 채널 · 분석 ·
  오토파일럿 · 검수 · 자료실 · ＋만들기 · 계정 · 로컬 AI · AI 지원 스냅샷 · 시스템 · 상태.
* Content column `max-w-6xl`, card grid.

## Priority (§26)
`CREATE → STATUS → REVIEW → RESULT → ALERT`. Home leads with "오늘 무엇을 만들까요?"
(Topic / References / Execution Mode / SNS / Quality / Estimated Cost →
[콘텐츠 만들기]), then Current Jobs, Review Required, Recent Contents, Today's
Plan, Performance/Cost summary — not a wall of cards.

## Design system
`.card` / `.card-p`, `.btn-primary` / `.btn-ghost`, `.chip`, `.kv`, status
colours `ok`/`warn`/`danger`/`info`. One accent (`#4f46e5`). No gradient / glass /
heavy shadow. Loading = skeleton/partial; empty = action hint; error = cause +
fix action.

## Screens (existing, kept — no regression)
홈 (`/`), 콘텐츠 (`/library` gallery+table, server pagination, video preview,
detail, platform versions, history, governance, analytics, revenue), 콘텐츠 상세,
Video Studio (`/campaigns/[id]/studio`), AI 학습실 (`/learn-studio`), 분석
(`/analytics`), 수익, 캘린더 (`/calendar` month/week/day), 검수 (`/governance`),
설정/로컬 AI (`/settings/local-ai`), 계정 (`/publishing`), 시스템 (`/admin`), 상태
(`/system`), **AI 지원 스냅샷 (`/support`)**.

## Responsive
Verified at 1440×900 / 1280×720 / 1024×768 via `next build` + HTTP-level journeys.
`tsc` + `next build` clean.
