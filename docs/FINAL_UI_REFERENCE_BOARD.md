# FINAL UI REFERENCE BOARD

> Consolidated reference set for the AI Content Factory visual system.
> Companion to `docs/FIGMA_DESIGN_REFERENCE_AUDIT.md` (dashboard templates) and
> `docs/3D_WEB_REFERENCE_AUDIT.md` (WebGL). We extract *patterns* only - no
> template is adopted whole, no asset is copied.

## References

| # | Name | Source | We reference for | Good | Bad / not for us | Patterns we USE | Patterns we REJECT |
|---|---|---|---|---|---|---|---|
| 1 | **Linear** | linear.app | App shell, command UX, density, keyboard | Near-black surface ladder, restrained accent, Cmd-K, tight vertical rhythm, hairline borders not shadows | Marketing-site polish that does not translate to data screens | Dark surface ladder, `Cmd-K` palette, one accent, hairline dividers, negative-tracked display type | Big atmospheric gradients on content, oversized hero type on inner pages |
| 2 | **Vercel dashboard** | vercel.com/dashboard | Data screens, tables, deploy/status lists | Calm neutral surfaces, excellent table + list density, clear status chips, generous but purposeful whitespace | Occasionally too sparse for an ops tool | Table row density, status chip language, list-over-card for logs/history, empty-state tone | Card-for-everything |
| 3 | **Raycast** | raycast.com | Command composer, spatial minimalism | The command bar as the primary surface; results list; quiet chrome | Consumer-launcher scale, not multi-page product | CommandComposer shape (one line + contextual chips + primary action), quiet nav | Full-screen launcher framing |
| 4 | **Notion** | notion.so | Settings, forms, side panels, content editing | Label-above-input, grouped settings sections, side peek panel, restrained buttons | Blocks/editor model is not our domain | Settings section grouping, side-peek inspector, button hierarchy (primary/secondary/ghost) | Everything-is-a-block |
| 5 | **Figma (app)** | figma.com | Left panel navigation, right inspector, canvas + panels composition | Persistent left nav with labels, right contextual inspector, the canvas is the workspace with panels floating at the edges | Design-tool specifics | **Canvas-as-workspace with edge panels** -> our 3D studio + floating panels, left nav with labels, right inspector on select | Toolbar clutter |
| 6 | **Vision UI Dashboard** | Creative Tim (Chakra, MIT) | Dark surface hierarchy, glass panels, stat tiles | Translucent navy glass panels + blur + inner top highlight; gradient reserved for stat emphasis | Literal navy palette; rainbow charts; VR/auto demo pages | `--surface-floating` / `.panel` treatment, gradient-for-hero-stat-only | Navy `#0f1535`, multi-accent charts |
| 7 | **Dashboards Layout Ideas** | Figma Community | Responsive re-composition | Shows mobile as re-architecture: nav transformation, priority stacks, progressive disclosure, filter overlays | It is a study, not a product | Per-breakpoint IA, left-nav -> bottom-nav, filters -> full-screen overlay on mobile | - |
| 8 | **Horizon UI** | horizon-ui.com (Chakra, MIT) | Functional-screen components | Clean forms, tables, status, settings; a genuinely designed light mode | Reads as an admin template if used as the shell | Component patterns for 설정 / 표 / 상태 only; real (non-inverted) light mode | Horizon nav/hero/shell |
| 9 | **Analytics Dashboard** | Figma Community | 분석 / 수익 structure | Question-led sections, one hero metric + delta, trend before number | Widget-wall density | Section = the question it answers; hero metric + delta; chart then "so what" | Chart gallery |
| 10 | **Spline Showcase / R3F examples / Three.js showcase** | spline.design/community, r3f.docs.pmnd.rs, threejs.org | Home 3D studio only | Transmissive glass, restrained bloom, slow motivated camera, edge-bled scenes, progressive load | Full-scene scroll-hijack, heavy asset payloads | Transparent edge-masked canvas, `frameloop`/`PerformanceMonitor`, one focus move per intent, procedural geometry | GLB character packs, neon HUD frames, CAD-style orbit |

## Composition decision (which reference drives which surface)

| Surface | Primary reference(s) |
|---|---|
| App shell (nav rail + command bar) | Linear + Figma (left nav with labels, right inspector) |
| Command composer | Raycast + Vision UI (glass panel) |
| 3D studio on Home | Figma canvas-as-workspace + Spline/R3F showcase (edge-bled, procedural) |
| Content Library | Vercel (table density) + Vision UI (poster gallery, glass filters) |
| 검수 (Review) | Figma inspector model + Notion side-peek |
| Analytics / Revenue | Analytics Dashboard (question-led) + Linear density |
| Settings | Notion + Horizon UI (grouped sections, forms) |
| Responsive | Dashboards Layout Ideas (per-breakpoint IA) |
| Light mode | Horizon UI (designed, not inverted) |

## Non-negotiables carried from references

- Dark surface ladder + ONE accent (lavender `#5e6ad2`); no second chromatic colour, no neon glow stacks.
- Left navigation shows **icon + Korean label by default**; collapse is user-opt-in with tooltips.
- The 3D canvas is transparent + edge-masked; it must never read as a bordered box.
- Card only when elevation means hierarchy; otherwise list / table / timeline / inspector / split view.
- Empty state = a sentence + a CTA, never a wall of "0" tiles.
- No internal enums / dev jargon in user-facing text ("fixture registry", `facebook_reel`, raw status codes).
