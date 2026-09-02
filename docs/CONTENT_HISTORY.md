# CONTENT HISTORY — Phase 8

> Part of the Content Library detail (`history` tab). Code:
> `app/library/service.py::_history`.

Shows, ordered by time:

- **Script versions** — each `Script` row (master + per-platform), with word count.
- **Asset versions** — per `asset_type` (video / thumbnail / image / audio /
  subtitle / render), the first is `ORIGINAL`, later ones `REVISION`, the last is
  marked `current`.
- **Governance changes** — `GovernanceEvent` rows (`<kind> -> <to_state>`).

Scene changes, prompt-version changes and platform-selection changes are visible
through the related tabs (`media`, `platform_versions`) and the Prompt Lab.

Reopen actions (spec §44) are surfaced in the UI: open / view video / prepare to
publish / view analytics / make a new version. Adding a platform later
(`add-platform`) only generates the new platform's adaptation + media.
