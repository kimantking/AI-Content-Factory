# VISUAL DIRECTION V3 - "Neural Operations Studio"

> The V2 result was judged a **DESIGN FAIL**: the app still read as a white admin
> template with a black 3D rectangle dropped into it. Root cause: the theme
> defaulted to the OS setting (light), so users saw the light admin theme + a
> hard-bordered opaque dark canvas. V3 fixes the *presentation layer* only -
> no new features, no backend change, no regressions.

## Product concept

**AI CONTENT FACTORY — Neural Operations Studio.** A premium interactive 3D web
application that is also a real content-operations control center. "My AI staff
are working in a studio" + "this is a serious ops system, not a game."

## The five failures V3 must reverse

| V2 fail | V3 fix |
|---|---|
| Light admin shell by default | **Dark is the default** (not OS-derived). Light stays as an opt-in, separately designed (not an inversion). |
| 3D inside a black bordered `<canvas>` box | **Transparent canvas**, no border, edge-masked so the scene melts into the page. It is the workspace surface, not a widget. |
| 2D and 3D look like two products | Shared token system; 2D UI is **translucent glass panels floating over/into** the scene; one accent, one type system, one motion language. |
| Generic form-first composer | **Command composer** - one large prompt line, contextual chips, cost + CTA. |
| No identity | Spatial workspace + Korean ops language + the agent studio is unique to ACF. |

## Design tokens (extends `DESIGN.md`, does not replace it)

Keep every DESIGN.md hex. Add:

```
--canvas            #010102   (unchanged)
--canvas-atmos      radial-gradient(120% 80% at 50% -10%, rgba(94,106,210,0.10), transparent 60%)
                              layered on --canvas for depth (body::before, fixed, -z)
--surface-1..4                (unchanged - opaque cards on plain backgrounds)
--surface-floating  rgb(15 16 17 / 0.72) + backdrop-blur(18px)   (panels over the 3D scene)
--surface-glass-hi  inset 0 1px 0 rgb(255 255 255 / 0.06)         (rendered-glass top highlight)
--hairline*                    (unchanged)
--primary #5e6ad2 / hover #828fff / focus #5e69d1   (unchanged - THE only accent)
--success #27a644              (unchanged - only semantic colour)
--attn    #7a7fad (brand-secure)  warnings; error = icon + weight, no red
```

Typography, radius, spacing scales = DESIGN.md unchanged. Display = Inter 600/700 negative-tracked; body = Inter; mono = JetBrains Mono.

## Composition

### Desktop (>= 1024px)
- **NavigationRail** (left, 60-76px, icon-first, near-black, hairline-right, hover label / active lavender bar). Collapsible to full 236px labelled.
- **CommandBar** (top, 56px, transparent over canvas, wordmark + global search (Cmd K) + health dot + notifications + user). No card, no heavy border.
- **SpatialWorkspace** (main): the 3D studio is a **full-bleed band** behind the content (edge-masked top/bottom/right), ~520-620px tall on Home. The **CommandComposer** floats as a `surface-floating` panel overlapping the top of the scene. Priority cards (`현재 작업` / `검수 대기` / KPI bento) are `surface-floating` panels below, still visually "in" the studio via the atmos gradient continuing behind them.
- Agent click -> camera focus + **Inspector** as a `surface-floating` drawer, right.

### Tablet (768-1023)
- Rail collapsed to icons (or drawer). 3D kept but `quality="low"` (DPR 1, contact shadows off, fewer lights). Composer full-width panel above a 2-up card grid.

### Mobile (< 768px)
- **BottomNav**: 홈 / 콘텐츠 / + (만들기) / 검수 / 더보기(sheet). No sidebar.
- **No WebGL.** 3D -> the existing 2.5D `OfficeFallback` (4 station cards, real state colours) OR a single pre-rendered hero still. Composer full-width, platform/goal -> bottom sheets, advanced -> accordion.
- Priority stack: Composer -> 현재 작업 -> 검수 필요 -> Mini office -> 최근 콘텐츠 -> 알림. Analytics last.

## Component language

`NavigationRail` · `CommandBar` · `CommandComposer` · `SpatialWorkspace` · `FloatingPanel` (glass) · `Inspector` (glass drawer) · `MetricTile` (bento, gradient only for the hero metric) · `StatusSurface` (dot+label, never colour-only) · `MediaCard` (poster-first) · `DataPanel` (table container) · `EmptyState` / `ErrorState` (unchanged) · `Skeleton`.

Screens keep their existing components where they already fit (`Card`, `Metric`, `StatusBadge`, `DataTable`, `JobProgress`); those get restyled via tokens, not rewritten.

## Motion language

| Element | Motion |
|---|---|
| Navigation / route | 120-160ms opacity + 4px translate, ease-out |
| FloatingPanel / Inspector | 180ms slide + fade, spring-ish (no bounce) |
| 3D camera | damped lerp, ~500ms settle, one move per intent |
| 3D agent | idle: none (calm) or <=2% breathing when working; working: monitor emissive pulse |
| Job progress | width/opacity only |
| Notification | fade + 6px rise |
All gated by `prefers-reduced-motion` (global CSS already does duration -> 0.001ms).

## Responsive strategy

Per breakpoint we re-decide **information priority, navigation, 3D presence, panel layout, form layout, chart layout, action placement** - not CSS scaling. Details in `docs/RESPONSIVE_DESIGN.md`. Verified breakpoints: 1440, 1280, 1024, 768, 430, 390, 375.

## Figma pattern matrix

| Need | Reference | What we take |
|---|---|---|
| Dark surface hierarchy + glass panels | Vision UI | `surface-floating`, inner-top-highlight, gradient-for-stat-only |
| Responsive re-composition | Dashboards Layout Ideas | nav transformation, priority stacks, progressive disclosure |
| Functional components (settings/tables/status) | Horizon UI | label-above-input, grouped sections, table density, real light mode |
| Analytics structure | Analytics Dashboard | question-led sections, hero metric + delta |
| Profile / settings | Purity UI | account block composition |
| Spatial 3D workspace | (custom) | 3D as the workspace surface, UI floating in it |

## This-session scope

1. Docs (this file + `FIGMA_DESIGN_REFERENCE_AUDIT.md` + touch `DESIGN_SYSTEM.md`, `RESPONSIVE_DESIGN.md`, `PROJECT_STATE.md`).
2. Dark-default; token additions (`--canvas-atmos`, `--surface-floating`).
3. De-box the 3D: transparent canvas, edge mask, full-bleed, composer floats over it.
4. Shell premium pass (rail + command bar chrome).
5. CommandComposer redesign.
6. Home responsive (desktop / tablet / mobile) verified in-browser, before/after.
7. Other screens inherit tokens + shell; deep per-screen redesign is follow-up.

Out of scope this session: deep redesign of Library / 학습실 / Analytics / Revenue / Review / AI Support internals; the Autonomous Learning subsystem (separate brief).
