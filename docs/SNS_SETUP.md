# SNS Setup (Phase 10 §12-§15)

Capability registry: `app/publishing/capabilities.py` (per platform: auth,
content types, generation, publish, analytics, revenue, rate limit, app review,
account requirement, current state). API: `GET /api/publishing/platforms`.

Full status table: `docs/PLATFORM_SUPPORT_MATRIX.md`.

## Connecting a real account (§13)
1. OAuth via `/publishing` (or `/api/publishing/oauth/...`). Token encrypted with
   `ACF_MASTER_KEY` (Fernet), stored on `PlatformAccount`.
2. A **connected** account shows `connection_status = CONNECTED`. A mock/test
   account shows `integration_status = MOCK_TESTED`. **These are never the same
   badge.**
3. First action after connecting is, where the API allows, a **read-only account
   probe** — not a publish.

## Real publish safety (§14)
Phase 10 never triggers a remote publish on its own. Before any remote call the
UI shows: platform · account · content · preview · schedule · cost · governance ·
rights · disclosure. The worker (`app/publishing/engine.py::run_publish_job`)
re-checks, in order, right before the API call:
`GLOBAL_PUBLISH_PAUSE / EMERGENCY_STOP → PlatformSelectionGate → token validity
(CredentialGate) → GovernanceGate → RightsLedger expiry`. Cancellation and
idempotency (`idempotency_key` + `remote_post_id`) also apply.

## First real pilot (§15)
**1 content × 1 platform**, with explicit user approval. Private / unlisted where
the platform supports it. No "10 platforms × many channels" first publish.
