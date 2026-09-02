# Browser E2E (Phase 9 §72-§78)

## Status: HTTP-level E2E done; rendered-browser E2E = AVAILABLE_NOT_REQUIRED

The frontend has **no JS test runner** (no Playwright / Cypress / Vitest in
`frontend/package.json` or `node_modules`). Adding Playwright is a new dev
dependency that needs D67 approval, and a global install is disallowed by project
rules. So rendered-browser E2E was **not** run in this pass.

What was done instead:

1. **Frontend build gate** — `tsc --noEmit` **clean** and `next build` **clean**
   (all routes compile and statically analyse). See the Phase 9 report §FRONTEND.
2. **HTTP-level end-to-end journeys** — `tests/phase9/test_e2e_journeys.py` drives
   the exact API sequence each frontend page calls, for all six journeys:

| # | journey | §ref | asserts | result |
|---|---|---|---|---|
| 1 | Beginner: topic → cost preview → create → result → library → governance view | §73 | campaign SUCCESS, appears in library search, detail + governance views 200 | PASS |
| 2 | Learning: 10 mock refs → LEARN_ONLY → job DONE | §74 | `POST /api/references` 201, **campaign count unchanged** (0 production) | PASS |
| 3 | Edit: scene 3 → `POST /api/library/{id}/edit-plan` | §75 | impact `rebuild_scene_clips == [3]`, scenes 1/2/4 untouched, `regenerates_ai_visuals` | PASS |
| 4 | Platform add-later: YT-only campaign → add `instagram_reel` | §76 | YT `PlatformContent` ids unchanged after the add | PASS |
| 5 | Review: `GET /api/governance/review` | §77 | 200, structured | PASS |
| 6 | Mobile: `GET /api/governance/cases`, `GET /api/library?page_size=10` | §78 | 200 (viewport-agnostic API) | PASS |

## To add real browser E2E later (needs D67 approval)

```bash
cd frontend
npm i -D @playwright/test           # project-scoped, NOT global
npx playwright install chromium
# e2e/ specs driving http://localhost:3000 against a running backend
```

Recommended first specs: the six journeys above, plus a mobile-viewport
(`devices['iPhone 13']`) run of the Review Center approve/hold flow.
