# SETUP WIZARD — Phase 8

> UI: `frontend/app/setup/page.tsx` (`/setup`). Progress is persisted to
> `localStorage["acf_setup_wizard"]` — resumable after closing the browser or an
> app restart.

## Steps (spec §11)

1. **워크스페이스** — name (existing workspaces listed).
2. **브랜드** — first brand name.
3. **SNS** — pick platforms to publish to (account connection is done later in
   `/publishing`).
4. **AI 제공자** — confirm whether an Anthropic key is set in `.env` (optional;
   local AI covers most features).
5. **로컬 AI** — "연결 확인" calls `/api/local-ai/status`; "간단 추론 테스트" calls
   `/api/local-ai/ping`. Models are never auto-downloaded.
6. **스타일** — default quality preset.
7. **예산 / 안전** — per-campaign budget; note that budget pressure shifts work to
   local/cache and reduces candidates, but never bypasses fact/governance/security.
8. **테스트 실행** — a DRY-RUN pass with no real publish.

"설정 완료" links to `/create`. "초기화" clears the saved wizard state.
