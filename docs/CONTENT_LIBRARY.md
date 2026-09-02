# CONTENT LIBRARY — Phase 8

> Code: `backend/app/library/` (read model), `app/api/routes_library.py`.
> UI: `/library`, `/library/[id]`.

## Purpose

The central store view of EVERY content the factory has ever produced — including
content made before Phase 6 tenant scope, Phase 7 governance, and the Intelligence
Upgrade. It is **not a new table**: it aggregates `Campaign`, `PlatformContent`,
`Asset`, `Script`, `Publication` / `PublishJob`, `AnalyticsSnapshot`,
`RevenueEntry`, `CostLog`, plus (when present) `ReferenceSource`,
`GovernanceCase`, `RightsManifest`.

## Discovery (spec §35)

`list_content()` walks every `Campaign` (workspace-scoped for a tenant caller) and
builds a card per campaign. Legacy campaigns — `workspace_id IS NULL` **and** no
`execution_mode` — get a `LEGACY` badge and never crash: missing governance shows
as `NOT_APPLICABLE`, missing metrics as `—`.

## Card / table fields (spec §36-§38)

Card: thumbnail (or "영상 있음/없음"), topic, brand/channel, platforms, created,
duration, status, governance (`OK`/`REVIEW`/`BLOCKED`/`NOT_APPLICABLE`), publish
state (`PUBLISHED`/`SCHEDULED`/`DRAFT`/`BLOCKED`/`NOT_PUBLISHED`), views, revenue.
Table adds cost / profit. Search matches topic + script body; filters:
workspace/brand/channel/platform/content-type/status/governance/publish-state;
sort: newest/oldest/views/revenue/profit. Server-side pagination
(`content_library_page_size`, default 30).

## Detail tabs (spec §39)

`overview · preview · script · platform_versions · media · references · learning ·
governance · publishing · analytics · revenue · history`
(`GET /api/library/{id}` or `/{id}/{tab}`).

## Video preview (spec §40, §41)

`GET /api/library/{id}/media/video` streams the real MP4 from disk when it exists
(`FileResponse`, `video/mp4`). The detail preview reports width/height/fps/size/
version from the `render` asset. Sample renders whose path contains
`advanced_short` / `advanced_trend_short` / `advanced_explainer` / `sample` /
`demo` are flagged `is_demo` and shown as **DEMO / 테스트**, never as production.

## Platform versions + add-later (spec §42, §45)

Each `PlatformContent` under a campaign is a child version; a platform with no row
shows `NOT GENERATED`. `POST /api/library/{id}/add-platform` adds a platform to an
existing campaign's selection (and `Campaign.platforms`) so the media pipeline
builds **only** that platform — existing platforms are never regenerated, and a
platform already generated/selected is rejected (409).

## History (spec §43)

Script versions, per-asset-type versions (`ORIGINAL` vs `REVISION`, `current`
flag), and governance events, ordered by time.

## Legacy compatibility (spec §46, §85)

Verified: a pre-governance campaign with a real MP4 + publication is discovered,
its detail renders without error, `governance` is `NOT_APPLICABLE`, the video is
playable, and revenue/analytics/history populate from the existing rows
(`tests/library/`).
