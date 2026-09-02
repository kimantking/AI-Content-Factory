# AI Content Factory — Release v1.0.0

**Version:** `1.0.0` (`config.app_version`, surfaced at `GET /api/support/version`,
in the FastAPI OpenAPI, on `/support`, and in the AI Support Snapshot).
**Date:** 2026-09-01. **Phase:** 10 — Production V1.0 Final Integrated Release.

## What v1.0 is

The Phase 1–9 system, finished as a usable **product**:

* Full content pipeline (research → fact-check → strategy → hook → script → media
  → governance → publish) on LangGraph with a Postgres checkpointer.
* Model Execution Gateway → PromptComposer → Model Router → Provider, with local
  Ollama (`gemma3:4b`) as the light-task engine. **Direct provider bypass = 0.**
* Multi-brand / multi-channel, RBAC + tenant isolation, transactional hierarchical
  budgets.
* Content Governance pre-publish gate (rights / policy / originality / AI
  disclosure / claims), fails safe.
* Cross-Phase Intelligence (URL learning, reference datasets, prompt distillation,
  learned skills, LEARN_ONLY / SNS-OFF invariants).
* Content Library at scale (P9-001 fixed — DB pagination), Autopilot,
  cross-channel capacity planner.
* **Responsive dashboard** — desktop control center + mobile-first flows, shared
  backend state.
* **AI Support Snapshot** — one screenshot-/copy-friendly diagnostic page.
* **Production kill switches** — GLOBAL_PUBLISH_PAUSE, GLOBAL_PAID_PROVIDER_PAUSE,
  EMERGENCY_STOP, SAFE_MODE, MAINTENANCE_MODE — DB-backed, wired to real gates.

## Verified baseline

| | |
|---|---|
| Migration head | `0011_medium_repair` (single head, additive-only, **0 new migrations in Phase 10**) |
| New dependencies | **0** (backend + frontend) |
| Backend regression | see `docs/PROJECT_STATE.md` "Verified" — 545 (Phase 9) + 27 Phase 10 targeted |
| Frontend | `tsc --noEmit` clean, `next build` clean |
| Secret scan | clean |
| Phase 9 invariants | all re-verified (`tests/phase9/test_invariant_recheck.py`) |

## Verdict

**B — V1.0 RELEASE CANDIDATE READY; REAL CREDENTIAL / INFRA VERIFICATION PENDING.**

Ready for a **controlled production pilot** (1 content × 1 platform, with explicit
user approval): **YES**.
Ready for **unrestricted full automation**: **NO** — needs the credential /
infrastructure items in `docs/KNOWN_LIMITATIONS.md` and a human-approved pilot.

## Release docs

`PRODUCTION_DEPLOYMENT.md`, `PRODUCTION_CHECKLIST.md`, `PRODUCTION_CONFIGURATION.md`,
`PROVIDER_SETUP.md`, `SNS_SETUP.md`, `PLATFORM_SUPPORT_MATRIX.md`,
`BACKUP_AND_RECOVERY.md`, `MONITORING_AND_ALERTS.md`, `INCIDENT_RESPONSE.md`,
`SECURITY_CHECKLIST.md`, `OPERATIONS_RUNBOOK.md`, `AI_SUPPORT_SNAPSHOT.md`,
`DESKTOP_DASHBOARD.md`, `MOBILE_DASHBOARD.md`, `DASHBOARD_REFERENCE_AUDIT.md`,
`OPEN_SOURCE_COMPONENTS.md`, `KNOWN_LIMITATIONS.md`.
