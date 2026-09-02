# MULTI-BRAND ARCHITECTURE (Phase 6)

One AI Content Factory safely running many Brands × Channels × Platform accounts ×
Content categories × Revenue models. Code: `backend/app/mb/`, `backend/app/auth/`,
`backend/app/db/models_mb.py`, migration `0007_multibrand`. Companions:
`CHANNEL_MANAGER.md`, `PORTFOLIO_MANAGER.md`, `MONETIZATION.md`, `SECURITY_MODEL.md`.

**Goal is not more channels — it is deciding, from data, which channel to make
what for, spend how much, publish where, grow, shrink, and which is actually
profitable.**

## 1. Resource hierarchy

```
Workspace  (top-level tenant; timezone, objective, daily/monthly hard budget)
 └─ WorkspaceMember (user × role: OWNER/ADMIN/EDITOR/PUBLISHER/ANALYST/VIEWER)
 └─ Brand  (identity: profile, voice_profile, visual_identity, risk_policy,
    │       disclosure_policy; own hard budget; ContentPillars)
    └─ Channel  (Brand + a platform; own objective, production_profile,
                 autopilot_mode, daily budget, schedule, lifecycle, brand_safety)
                 platform_account_id ── PlatformAccount (token, scoped to ws+brand)
```

PlatformAccount and Channel are **separate** (§11): one account can back several
content types.

## 2. New tables (migration 0007, all additive)

`users, workspaces, workspace_members, brands, channels, content_pillars,
channel_health_snapshots, channel_operating_plans, portfolio_snapshots,
portfolio_decisions, budget_allocations, budget_reservations, affiliate_programs,
affiliate_links, sponsor_deals, offers, content_routing_decisions,
asset_usage_history, channel_reports, portfolio_reports`.

Plus **NULLABLE** tenant-scope columns on pre-existing tables:
`campaigns.{workspace_id,brand_id,channel_id}`,
`platform_accounts.{workspace_id,brand_id}`,
`cost_logs.{workspace_id,brand_id,channel_id}`,
`revenue_entries.{workspace_id,brand_id,channel_id}`.
Legacy rows stay NULL = "unscoped / pre-Phase-6"; the 223-test pre-Phase-6 suite
is unaffected. Migration is `Base.metadata.create_all(tables=[…])` + `ADD COLUMN
IF NOT EXISTS` — no destructive DDL (§105).

## 3. Engines (`app/mb/`)

| Module | Role | LLM? |
|---|---|---|
| `scope.py` | tenant/resource authorization (get_workspace/brand/channel, scoped_query) — every scoped row is checked | no |
| `budget.py` | hierarchical hard budgets + **transactional** reserve/settle/release + `validate_hierarchy` | no |
| `channel_manager.py` | `ChannelHealthScore` (0–100, objective-weighted) + `ChannelOperatingPlan` + warmup / false-scale guards | no (LLM only for reposition strategy — DESIGN_ONLY) |
| `portfolio.py` | portfolio scoring by workspace objective + budget allocation (hard-capped, exploration floor) + recommendations (advisory, never auto-delete) | no |
| `routing.py` | `ContentRoutingDecision` (which brand/channel/platform) + cross-channel **cannibalization** guard | no |
| `monetization.py` | `MonetizationAgent` model-fit + `profit_center` (estimate/actual kept separate) + sponsor / commercial / affiliate-disclosure guards | no |

**Management cost (§102):** everything above is SQL + metrics + rules + scoring.
The Channel/Portfolio managers do **not** call an LLM per cycle. Schedule (§103):
daily lightweight health, weekly manager recommendation, monthly portfolio review
(configurable — the beat wiring is DESIGN_ONLY this phase; the engines are
callable now).

## 4. Isolation guarantees (proven)

- **Auth**: `/api/ops/*`, `/api/admin/*`, `/admin` require a valid key in
  production/staging (or `AUTH_ENFORCE=true`). `tests/mb/test_auth_rbac.py`.
- **RBAC**: capability→min-role; VIEWER can't write, EDITOR can't set budget,
  only OWNER manages the workspace, system-admin bypasses. Same tests.
- **Tenant isolation (IDOR)**: reading/patching another workspace's brand /
  channel / workspace → 403; list endpoints scoped. `tests/mb/test_isolation.py`.
- **Credential isolation**: a token scoped to ws-A/brand-A raises if used with
  ws-B or brand-B expectations. `tests/mb/test_isolation.py`,
  `token_manager.assert_credential_scope`.
- **Budget race**: two concurrent 60-unit reservations against a 100 hard limit →
  exactly one succeeds (row-lock serialised). `tests/mb/test_budget.py`.

## 5. Content flow (multi-channel)

`Trend Hunter (Phase 4)` → global candidate → `routing.route()` scores every
ACTIVE channel of every ACTIVE brand (brand `risk_policy` blocks are a hard 0) →
`cannibalization_status()` checks other channels' recent near-identical topics →
`budget.reserve()` (transactional, all levels) → scoped `Campaign`
(`workspace_id/brand_id/channel_id` set) → existing Phase 1-A/1-B/2 pipeline →
`budget.settle()` at actual cost → `portfolio.snapshot()` reflects it.
End-to-end in `tests/mb/test_e2e_and_pause.py::test_multi_channel_mock_e2e`.
Cross-channel failure isolation (a budget error on channel 1 doesn't stop
channel 2) is tested there too.

## 6. Pause / stop semantics (§122–§124)

- **Channel PAUSED** → no new campaigns for it; other channels unaffected;
  analytics still readable.
- **Brand PAUSED** → all its channels stop new production; other brands unaffected.
- **Workspace EMERGENCY_STOP** → workspace-wide halt, separate from the global
  system emergency stop (Phase 4/5). Other workspaces unaffected.
Tested in `tests/mb/test_e2e_and_pause.py`.

## 7. What is DESIGN_ONLY this phase

Full sidebar dashboard IA (§74–§81 — one `/portfolio` page is built),
cross-channel scheduler + capacity planner + production-slot queue (§45–§48),
channel-autopilot / portfolio-autopilot beat wiring (§50–§51), channel
repositioning strategy (LLM) (§53), new-channel wizard (§55), brand/channel
cloning (§57–§58), weekly/monthly report generators + email (§89–§91), load-test
fixtures (§119), asset library UI + reuse-history wiring (§40–§43), template
system (§44), strict worker-job tenant validator + full audit coverage. The
schema, engines, and API for the core loop are done and tested; these are
follow-on surface.
