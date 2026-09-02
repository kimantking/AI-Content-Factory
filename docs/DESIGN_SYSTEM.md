# DESIGN SYSTEM (V3)

Source of truth: `frontend/app/globals.css` + `frontend/tailwind.config.ts`.
Base palette/type/spacing = `/DESIGN.md` (Linear near-black). V3 adds atmosphere,
a floating-glass surface, and makes **dark the product default**.

## Theme

- **Default: dark.** `app/layout.tsx` pre-paint script sets `data-theme="dark"`
  unless `localStorage.acf-theme === "light"`. It no longer follows the OS. Light
  is opt-in via the toggle and is a *separately treated* theme, not an inversion
  (surfaces + shadow strategy differ; the 3D scene stays dark-tuned for now).

## Tokens (CSS custom properties, RGB triples)

| Token | Dark | Role |
|---|---|---|
| `--canvas` | `1 1 2` (#010102) | page background |
| `body::before` | radial lavender bloom (`--primary` @ 0.12 / `--primary-hover` @ 0.06) | atmospheric depth, fixed, behind everything |
| `--surface-1..4` | DESIGN.md | opaque cards on plain backgrounds |
| `--surface-floating` (`.panel`) | `rgb(14 15 17 / 0.68)` + `backdrop-blur(20px) saturate(1.4)` + inner-top-highlight + soft drop | **UI that floats over the 3D studio / atmos bg** (composer, AgentPanel, inspectors) |
| `--hairline*` | DESIGN.md (`--hairline-o` opacity knob) | borders / dividers |
| `--primary` / `-hover` / `-focus` | #5e6ad2 / #828fff / #5e69d1 | the ONE accent (brand mark, CTA, focus, active nav) |
| `--success` | #27a644 | only semantic colour |
| `--attn` (`--brand-secure`) | #7a7fad | warnings; error = icon + weight, never red |

Radius / spacing / type scales: unchanged from DESIGN.md. Fonts: Inter (display
600/700 negative-tracked; text) + JetBrains Mono, via `next/font` self-hosted.

## Component classes (`globals.css @layer components`)

`.panel` (glass) · `.card` / `.card-2` (opaque) · `.card-p` · `.btn` + `.btn-primary`/`-secondary`/`-ghost`/`-danger` · `.input` · `.chip` · `.kv` · `.t-display-*` / `.t-headline` / `.t-eyebrow` / `.t-mono`.

## React components

- Chrome: `components/AppShell.tsx` - **NavigationRail** (icon rail 60px, hover/toggle to 236px, near-black translucent + blur), **CommandBar** (transparent gradient, no border, wordmark + Cmd-K search + health dot + notifications + user), mobile **BottomNav** + "더보기" sheet, `CommandPalette` (Cmd-K).
- Shared UI: `components/ui/*` - `Icon`, `primitives` (`Card`, `CardBody`, `CardTitle`, `PageHeader`, `Metric`, `EmptyState`, `ErrorState`, `Skeleton`), `StatusBadge`, `DataTable` + `Pagination` + `useUrlState`, `JobProgress`, `ThemeToggle`.
- Studio: `components/office/*` - `OfficeStage` (full-bleed, edge-masked, transparent canvas, no box), `Office3D` (R3F + drei), `Workstation`, `AgentPanel` (glass), `OfficeFallback` (2.5D CSS), `office-data` (real-state derivation).
- `lib/status.ts` - the single enum -> `{ ko label, tone, icon }` map. No screen hand-rolls colour maps.

## Rules

- Dark is the reference. Never invent colours outside DESIGN.md + the tokens above.
- Accent is scarce: brand mark, primary CTA, focus ring, active nav, one hero stat.
- Status is never colour-only (always icon + label).
- Panels over the 3D studio use `.panel`; cards on plain screens use `.card`.
- The 3D canvas is transparent and edge-masked - it must never read as a bordered box.
- Motion honours `prefers-reduced-motion` (global CSS zeroes durations).
