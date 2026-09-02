# VISUAL DIRECTION V2 - "Neural Operations Studio"

> Same effort tracked as V3 in `docs/VISUAL_DIRECTION_V3.md` and
> `docs/DESIGN_SYSTEM.md` / `docs/RESPONSIVE_DESIGN.md`. This file holds the
> brief-mandated section structure. Presentation layer only - no features, no
> backend, no API/DB changes.

## Current problems (the FAIL)

1. Light "admin" theme by default (theme followed the OS; user's OS is light).
2. White NavigationRail 236px, bordered white header -> reads as an admin template.
3. Form-first Quick Create (title input + rows of tiny outlined buttons).
4. The 3D scene lived inside an opaque, hard-bordered black `<canvas>` box.
5. 2D UI (white) and 3D (black) looked like two different products.
6. Every card the same bordered rectangle; no depth, no atmosphere, no identity.

## Target aesthetic

Premium interactive 3D web application + AI operations control center + cinematic
spatial interface. Deep near-black environment, atmospheric lighting, one accent,
high-contrast Korean typography, floating operational panels over a spatial 3D
studio. Not a game; not an admin template.

## Color / surface system

Base = `/DESIGN.md` (near-black `#010102`, ink `#f7f8f8`, lavender `#5e6ad2` sole
accent, `#27a644` sole semantic). V2 additions:

- **`body::before`** fixed radial lavender bloom -> atmospheric depth behind everything.
- **`--surface-floating` / `.panel`** = translucent (`rgb(14 15 17 / 0.68)`) +
  `backdrop-blur(20px)` + inner-top highlight + soft drop -> for UI that floats
  over the 3D studio (composer, agent inspector).
- Opaque `.card` (`--surface-1..4`) stays for plain data screens.
- **Dark is the default** (bootstrap no longer follows OS). Light = opt-in, treated separately.

Surface ladder: `canvas(0)` -> `surface-1` (raised) -> `surface-2` (interactive/hover) -> `panel` (floating glass) -> overlay/scrim.

## Typography

DESIGN.md scale unchanged. Inter (display 600/700, negative tracking) + Inter text
+ JetBrains Mono, `next/font` self-hosted (no new downloads). Hierarchy:
`t-display-*` / page title (`PageHeader` h1, `text-[21px]->[26px]`) / `CardTitle`
h2 / `Metric` / body / `caption` / status. Korean line-break + tabular numerals audited.

## Navigation

- Desktop: **icon NavigationRail** 60px (near-black, translucent + blur, hairline
  right), hover/toggle to labelled 236px (persisted). Active = lavender icon + tint, not a grey box.
- Command bar: **transparent gradient**, no border, 56px - wordmark + Cmd-K global
  search + system-health dot + notifications + user.
- Mobile: **BottomNav** (홈/콘텐츠/+/검수/더보기) + "더보기" bottom sheet.

## Home composition

`AppShell` (rail + transparent command bar) > glass **CommandComposer** (sparkle
mark, "AI에게 만들 콘텐츠를 말하세요", command-style placeholder, chips, cost + CTA)
> **full-bleed 3D studio band** (transparent canvas, radial+vertical edge mask,
no border, `-mx` bleed, `h-[360/440/520]`) with a floating status label > priority
panels (현재 작업 / 검수 대기 / 최근 콘텐츠 / 오늘의 성과 / 오토파일럿) on the same
near-black canvas. Agent click -> camera focus + `.panel` glass Inspector (right / bottom-sheet).

## 3D composition

R3F + drei, fully procedural (no GLB). 4 stations (리서치/대본/영상/게시 에이전트) on
a floor platform; 3-point + lavender rim lighting; procedural desk/monitor/capsule
avatar/beacon; real-state driven (`office-data.deriveOffice(snap)` from the live
pipeline). Camera: damped isometric, <=2 deg pointer parallax, one focus move per
click. Perf: `frameloop`, `PerformanceMonitor` DPR tiering, `AdaptiveDpr`, no
realtime shadows; ~35 draw calls, <30k tris, 3D engine in a lazy chunk (~228 kB
gzip) that never touches the initial `/` bundle or non-3D routes.

## Motion

One system: navigation 120-160ms opacity+translate; panel/inspector 180ms
slide+fade (no bounce); 3D camera damped ~500ms; 3D agent idle none / <=2%
breathing when working; job progress width/opacity only; notification fade+rise.
All gated by `prefers-reduced-motion` (global CSS zeroes durations; 3D drops to
`frameloop="demand"`, static).

## Mobile

Re-composed, not scaled: BottomNav, no WebGL -> `OfficeFallback` 2.5D grid (same 4
stations, same real-state colours, tappable), full-width composer, platform/goal ->
sheets, advanced -> accordion. Priority stack: Composer -> 현재 작업 -> 검수 필요 ->
mini office -> 최근 콘텐츠 -> 알림; analytics last. Details in `docs/RESPONSIVE_DESIGN.md`.

## Page examples

- **Home**: above.
- **콘텐츠 보관함**: same dark language, poster-first gallery / `DataTable`, floating filters. (tokens applied; deep pass = follow-up)
- **AI 학습실**: intro line + [자료 추가] + learning flow (자료 수집 -> 분석 -> 패턴 -> 스킬 -> 적용) + 발견한 패턴 / 학습된 스킬 / 제작 규칙 / 최근 학습. (deep pass = follow-up)
- **검수**: large cinematic preview + `.panel` inspector (상태/거버넌스/권리/비용/플랫폼) + sticky 수정요청/보류/승인.
- **분석 / 수익**: no forced 3D, same system, question-led sections, hero metric + delta.
- **AI 지원**: diagnostic cockpit, health hero, capture mode + copy (Phase 10 contract kept).
