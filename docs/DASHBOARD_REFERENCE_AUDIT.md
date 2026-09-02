# Dashboard Reference Audit (Phase 10 §43-§46, §92)

**Method:** AUDIT → PATTERN EXTRACTION → LICENSE CHECK → SECURITY CHECK →
COMPONENT MAPPING → INCREMENTAL INTEGRATION. **No repository was cloned over the
frontend. No component file was copied.** Only structural / interaction patterns
were studied and re-implemented in the project's own stack
(Next.js 15 App Router + React 19 + Tailwind + hand-rolled components — no shadcn
runtime added).

## Repositories audited

| # | Repo | Stack | License | Verdict | What we took (as a *pattern*) |
|---|---|---|---|---|---|
| 1 | Kiranism/next-shadcn-dashboard-starter | Next.js App Router, shadcn, TanStack Table | MIT | REFERENCE_ONLY | URL-synced list state (page/query/filter as search params); server-side pagination as the default; a "table on desktop / card list on mobile" split |
| 2 | satnaing/shadcn-admin | Vite + React + shadcn | MIT | REFERENCE_ONLY (framework differs) | collapsible sidebar → our responsive top-nav + mobile bottom-nav + "더보기" bottom sheet; command-palette affordance; empty-state copy tone; density |
| 3 | reoring/next-shadcn-admin | Next.js port of #2 | MIT | REFERENCE_ONLY | Next App Router placement of the shell; mobile nav breakpoints (`md:`) |
| 4 | TailAdmin/free-nextjs-admin-dashboard | Next.js + Tailwind | MIT (free tier) | REFERENCE_ONLY | KPI card grid rhythm; calendar → agenda-on-mobile idea; operational status cards. **Pro-tier widgets explicitly NOT used.** |
| 5 | tremorlabs/template-dashboard-oss | Next.js + Tailwind + Tremor | Apache-2.0 (the *OSS* template) | REFERENCE_ONLY | analytics KPI hierarchy (headline number → delta → sparkline → detail); "answer a question, don't just draw a chart" framing |
| — | tremorlabs/template-dashboard (commercial) | — | **commercial / non-permissive** | **REJECT for code. REFERENCE_ONLY for visual study.** | nothing copied; layout ideas only |

### Additional candidates searched (GitHub, `next.js tailwind dashboard responsive`)

| Repo | License | Verdict | Reason |
|---|---|---|---|
| shadcn-ui/ui (examples/dashboard) | MIT | REFERENCE_ONLY | canonical card/table spacing; we don't add the shadcn CLI/runtime — too much dependency weight for the ~2 components we'd use |
| horizon-ui/horizon-tailwind-react-nextjs | MIT (free) | REJECT | heavy Chakra-adjacent styling, large dep tree, visual identity too strong to absorb cleanly |
| Kiranism/react-shadcn-dashboard | MIT | REFERENCE_ONLY | same patterns as #1, older |

## Scorecard (0–10; higher = better fit for AI Content Factory)

| Repo | Visual | Info Hierarchy | Nav | Desktop UX | Mobile UX | A11y | Tables | Analytics | Maintain | Stack Compat | License | Dep Weight | Integration Risk | ACF Fit | **Notes** |
|---|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| Kiranism starter | 8 | 8 | 7 | 8 | 7 | 7 | 9 | 6 | 8 | 9 | 10 | 6 (adds shadcn+tanstack) | med | 8 | best structural match; we borrow the *idea*, not the deps |
| satnaing admin | 9 | 8 | 9 | 8 | 8 | 8 | 7 | 6 | 8 | 4 (Vite) | 10 | n/a | low (pattern only) | 7 | best nav/UX polish to imitate |
| reoring admin | 7 | 7 | 8 | 7 | 8 | 7 | 6 | 5 | 6 | 8 | 10 | n/a | low | 6 | Next port of #2 |
| TailAdmin free | 7 | 7 | 6 | 7 | 7 | 6 | 6 | 7 | 6 | 8 | 8 | 5 | med | 6 | KPI grid + calendar ideas; avoid pro widgets |
| Tremor OSS | 8 | 9 | 6 | 7 | 6 | 7 | 6 | 9 | 7 | 7 | 9 | 5 (Tremor pkg) | med | 7 | analytics hierarchy; we do NOT add the Tremor package |

## Patterns SELECTED (re-implemented in our stack)

1. **Responsive shell** (`components/AppShell.tsx`) — sticky top bar with the
   product name + version + a persistent "AI 지원" link; a grouped desktop nav
   (`hidden md:flex`); a 5-slot mobile bottom nav (홈 / 콘텐츠 / ＋만들기 / 검수 /
   더보기) with a bottom-sheet for the rest. Inspiration: satnaing sidebar + the
   iOS-style tab bar; **implementation is ours**.
2. **Design tokens** (`tailwind.config.ts` + `globals.css` `@layer components`) —
   one accent (`#4f46e5`), calm surfaces, semantic status colours, `card` /
   `btn-*` / `chip` / `kv` classes. No gradients / glass / heavy shadow.
3. **URL-synced list state** — Content Library already does server pagination;
   Phase 10 keeps that and does not regress to full preload.
4. **KPI hierarchy** (Analytics) — headline number → delta → detail; Actual vs
   Estimated always labelled.
5. **Diagnostic surface** (AI Support Snapshot) — a single screenshot-friendly
   page. This one is **CUSTOM** — no reference dashboard has an equivalent.

## Patterns REJECTED

* Whole-template adoption / `git clone` over `frontend/` — forbidden (§49).
* Adding shadcn CLI + Radix + TanStack Table + Tremor + a chart lib + an icon
  library — dependency bloat (§93) for a handful of components we can hand-roll.
* Auth/RBAC/state/API-convention swaps from any template (§49) — untouched.
* Commercial Tremol/Tremor template code — REJECTED for copy (§44).

## Security review (§48)

No external `README` command / install script / `postinstall` / workflow /
binary was executed. Only `LICENSE`, `package.json`, and representative source
were read. No dependency was added from any reference repo.

## Result

The dashboard is now **AI Content Factory's own design system** — a restrained
SaaS control-center look — informed by the above, transplanted from none.
See `docs/DESKTOP_DASHBOARD.md`, `docs/MOBILE_DASHBOARD.md`,
`docs/OPEN_SOURCE_COMPONENTS.md`.
