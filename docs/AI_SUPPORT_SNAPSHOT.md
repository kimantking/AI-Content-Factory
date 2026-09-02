# AI Support Snapshot (Phase 10)

A single read-only diagnostic a user can **screenshot** or **copy** and hand to
ChatGPT / a support engineer to diagnose a problem with minimal follow-up.

## Where
* UI: `/support` ("AI 지원 스냅샷"). Linked from the top bar (always visible) and the
  mobile "더보기" sheet.
* API: `GET /api/support/snapshot` (JSON), `GET /api/support/snapshot.txt` (copy
  text), `GET /api/support/version`.
* Backend: `app/support/snapshot.py` (`build_snapshot`, `snapshot_text`),
  `app/support/errors.py` (code normaliser + suggested actions),
  `app/api/routes_support.py`.

## What it shows (all from real sources — no frontend hardcoding)
| Section | Source |
|---|---|
| version / environment / time / overall health | `config`, `ops.health` |
| kill switches (publish pause / paid provider pause / emergency / safe / maintenance) | `ops.runtime_flags` |
| system: backend / DB / Redis / workers / scheduler / storage / FFmpeg / Ollama / local model / cloud summary / publisher summary | `ops.health`, `worker_registry`, `queue_backpressure`, provider registry |
| current jobs (campaign id, brand, channel, mode, stage, elapsed, agent runs) | `Campaign` + `AgentRun` |
| pipeline (research…publish, WAITING/RUNNING/DONE/FAILED) | `Campaign.current_step` + `AgentRun` |
| model routing (agent, task, provider, model, tier, reason, fallback, escalated, PromptComposer used) | latest `ModelRoutingEvent` |
| Ollama (reachable, model available, last error) | live `OllamaLLMProvider.health()` |
| workers / queues (online, busy, stale, depths, publish failed/retry/dead-lettered) | `worker_registry`, `queue_backpressure`, `PublishJob` |
| last error (timestamp, **normalised error code**, class, service, message, retryable, **suggested action**, trace id) | latest `ErrorLog` |
| recent events (last ~10) | `AgentRun` |
| governance / platform selection / cost (estimated / actual / budget / pricing-unknown) | `Campaign`, `CampaignPlatformSelection`, `CostLog` |
| learning (references, processed, duplicates, datasets, skills, blueprints) | latest `LearningJob` |
| test block (migration head) — non-prod / admin only | `alembic_version` |

## Error codes → suggested action (`app/support/errors.py`)
`OLLAMA_UNAVAILABLE`, `MODEL_OUTPUT_SCHEMA_INVALID`, `PROVIDER_RATE_LIMITED`,
`VIDEO_PROVIDER_TIMEOUT`, `DB_CONNECTION_FAILED`, `REDIS_UNAVAILABLE`,
`RENDER_FFMPEG_FAILED`, `STORAGE_WRITE_FAILED`, `PUBLISH_AUTH_EXPIRED`,
`GOVERNANCE_BLOCKED`, `BUDGET_EXCEEDED`, `PLATFORM_DISABLED`, `WORKER_STALLED`,
`INSUFFICIENT_RESEARCH`, `PUBLISH_PAUSED`, `PAID_PROVIDER_PAUSED`, `UNKNOWN`.
Each maps to a one-line Korean "do this next". Raw stacktrace is never shown on
the default screen.

## Capture mode & copy
* **[캡처 모드]** — toggles `body.capture-mode`: hides the nav/chrome (`[data-chrome]`)
  and the controls (`.capture-hide`), white background, so one desktop screenshot
  captures the whole diagnostic.
* **[지원 정보 복사]** — copies `snapshot.txt` (a fixed key-order block starting
  `AI CONTENT FACTORY SUPPORT SNAPSHOT`) to the clipboard, ready to paste into
  ChatGPT.

## Privacy / RBAC (verified — `tests/phase10/test_support_snapshot.py`)
* **Secret redaction** — the whole payload passes through `app.ops.redaction`
  (keys + value patterns: Bearer, `gh?_`, `sk-`/`sk-ant-`, Stripe, `ya29.`,
  AWS `AKIA`, Slack `xox*`, JWT, Fernet, DSN-with-password). Verified: planted
  keys / tokens / DSN passwords never appear in JSON or copy text.
* **Tenant scope** — a normal user sees only their workspace's jobs / errors /
  learning; `ctx.assert_workspace()` is the IDOR guard. A system admin gets infra
  detail (worker list, storage). Other tenants' data = 0.
* **Test block** — hidden for non-admin users in `production`.

## Mobile
Same content, single-column, priority order: overall → current job → pipeline →
last error → Ollama/model → governance → platforms → cost → trace. Readable from
one phone screenshot.
