# FIGMA DESIGN REFERENCE AUDIT

> Pre-implementation research for the V3 visual rebuild ("Neural Operations Studio").
> Date: 2026-09-02. Method: Figma Community landing pages are served behind
> CloudFront bot-blocking and could not be screenshotted from automated Chrome;
> the underlying templates (Vision UI / Horizon UI / Purity UI) are open-source
> Chakra dashboards with public repos + live demos, which were researched instead.
> We learn **layout, spacing, hierarchy, surface treatment, responsive behaviour**
> - never copy assets, illustrations, or whole layouts.

---

## Reference matrix

### A. Vision UI Dashboard (Chakra) - `figma.com/community/file/1060952013207459371`
- **Repo/demo**: `github.com/creativetimofficial/vision-ui-dashboard-chakra` (MIT), `demos.creative-tim.com/vision-ui-dashboard-chakra`
- **Visual strengths**: deep navy-black canvas (~`#0f1535` / `#030c1d`); cards are translucent navy **glass panels** (linear-gradient over `rgba(navy)` + `backdrop-blur`) with hairline light borders and a faint inner top highlight; gradient stat tiles; white primary text, muted blue-grey secondary; purple/blue accent used sparingly on charts + CTAs; generous card padding.
- **Responsive strengths**: sidebar -> off-canvas drawer < 992px; stat row 4-up -> 2-up -> 1-up; charts keep aspect and stack.
- **Patterns learned**: `surface-floating` = translucent panel + blur for anything sitting over a busy/3D background; inner-top-highlight for "rendered glass" depth; gradient reserved for *stat emphasis only*, never section fills.
- **Rejected**: literal navy `#0f1535` (we stay on DESIGN.md near-black `#010102`); rainbow chart palette; the VR/automotive demo pages; heavy multi-stop gradients.
- **License**: MIT (code). Figma file: Creative Tim community terms - **layout/pattern reference only, no asset reuse**.
- **Classification**: **REFERENCE_ONLY** -> glass FloatingPanel treatment + stat-tile hierarchy adopted, rebuilt in our tokens.

### B. Dashboards Layout Ideas - `figma.com/community/file/1208363071768116045`
- **Nature**: a pattern collection (many desktop/tablet/mobile layout variants), not a product.
- **Responsive strengths (the reason it's in the brief)**: shows that mobile is a *re-composition*, not a scale-down - left nav -> bottom bar (3-5 items) + "more" sheet; filter/sort sidebars -> full-screen overlay; multi-column KPI grids -> single-column priority stack; secondary content -> progressive disclosure (accordion/tab/drawer); F/Z-pattern priority placement.
- **Patterns learned**: our responsive strategy (see `docs/RESPONSIVE_DESIGN.md`) - per-breakpoint information priority, navigation transformation, `progressive disclosure` for anything not top-priority.
- **Rejected**: nothing to reject (it's a method, not a style).
- **License**: community pattern reference.
- **Classification**: **REFERENCE_ONLY (method)** -> drives the breakpoint strategy.

### C. Horizon UI - `figma.com/community/file/1098131983383434513`
- **Repo/demo**: `github.com/horizon-ui/horizon-ui-chakra` (MIT), `horizon-ui.com`
- **Visual strengths**: clean component set (70+), polished dark **and** light variants for every component, tidy form controls, data cards, tables, settings pages, status chips. Rounded ~16-20px cards, soft shadows in light / hairline borders in dark.
- **Patterns learned**: component-level patterns for the **functional screens** (설정 / 계정 / 표 / 상태): label-above-input, grouped setting sections, table row density, chip status language, two-column settings layout. Also: a genuinely designed light mode (not an inversion) - both themes share structure, differ in surface + shadow strategy.
- **Rejected**: using Horizon as the **app shell** - it is an admin template and reads as one; we take component patterns, not the chrome. No Horizon nav, no Horizon hero.
- **License**: MIT (code) / community terms (Figma).
- **Classification**: **REFERENCE_ONLY (functional components)**.

### D. Analytics Dashboard - `figma.com/community/file/1152266255337829742`
- **Nature**: analytics-focused layout study.
- **Visual strengths**: KPI hierarchy (one hero metric + supporting row), trend-first presentation (sparkline/area before big numbers), chart-per-question layout, comparison framing (vs. previous period), data storytelling captions.
- **Patterns learned**: 분석 / 수익 / 채널 성과 / 콘텐츠 성과 screens - lead each section with the *question it answers*, hero metric + delta, then the chart, then the "so what" line. No chart gallery.
- **Rejected**: dense multi-widget "cockpit" wall; decorative donut stacks.
- **License**: community reference.
- **Classification**: **REFERENCE_ONLY** -> analytics section structure.

### E. Purity UI Dashboard (Chakra) - `figma.com/community/file/1020707462188017225`
- **Repo/demo**: `github.com/creativetimofficial/purity-ui-dashboard` (MIT)
- **Visual strengths**: profile / settings / forms / secondary dashboard components; light, airy, well-spaced.
- **Patterns learned**: profile + settings composition only (avatar block, grouped account fields, billing rows).
- **Rejected**: as a Home/primary design - it is light-admin by nature. Not used for main screens.
- **License**: MIT / community terms.
- **Classification**: **REFERENCE_ONLY (profile/settings only)**.

---

## Additional Figma exploration (brief section 2)

Searched Figma Community themes: *AI Dashboard, Dark SaaS Dashboard, Creator Studio, Command Center, Operations Dashboard, 3D Web / Web3 Dashboard*. Common high-quality traits across the strong results (scored subjectively for fit):

| Trait | Take / reject |
|---|---|
| Near-black canvas + one indigo/violet accent + translucent glass panels | **Take** - matches DESIGN.md, extends it with `surface-floating` |
| Spatial hero (large visual band, UI floating over it, edges bled/masked) | **Take** - directly fixes the "black rectangle widget" fail |
| Bento KPI grids with mixed tile sizes | **Take** for Home priority row + Analytics |
| Command-bar / chat-style primary input | **Take** - QuickComposer redesign |
| Bottom-sheet platform/goal selectors on mobile | **Take** |
| Neon glow stacks, cyberpunk HUD frames, animated grid backgrounds | **Reject** (brief 8) |
| Full-bleed marketing gradients, 3-equal-card feature rows | **Reject** |
| Web3 "connect wallet" chrome, token tickers | **Reject** (irrelevant) |

**Originality-risk control**: no single template is adopted as the shell. The composition (spatial 3D workspace + floating glass product UI + Korean-first ops language) is specific to AI Content Factory and not present in any reference.

---

## License / asset rule (applied)

- Figma Community files: treated as **pattern reference only**. No images, icons, illustrations, 3D assets, or component code copied.
- Open-source repos (Vision/Horizon/Purity, all MIT): could be depended on, but **not added** - we already have Tailwind + our own `components/ui/*`; we reimplement the *patterns* in our token system.
- What we take: layout grids, spacing rhythm, surface hierarchy, hierarchy of emphasis, responsive transformations, interaction patterns.

---

## Pattern -> destination

| Source | Pattern | Applied to |
|---|---|---|
| Vision UI | translucent glass panel + blur + inner-top-highlight | `surface-floating` token, FloatingPanel, AgentPanel, composer-over-scene |
| Vision UI | gradient reserved for stat emphasis only | Home KPI hero tiles |
| Layout Ideas | mobile = re-composition, nav transformation, progressive disclosure | `docs/RESPONSIVE_DESIGN.md`, all screens |
| Horizon UI | functional component patterns, real light mode | 설정 / 계정 / 표 / 상태, light theme |
| Analytics Dashboard | question-led sections, hero metric + delta | 분석 / 수익 |
| Purity UI | profile/settings composition | 설정 profile block |
| (custom) | spatial 3D workspace with UI floating over blended-edge scene | Home shell |
