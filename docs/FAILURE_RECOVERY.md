# Failure & Recovery Testing (Phase 9)

Fault injection uses the built-in registries — no real outage needed:

* `app.providers.faults` — `faults.arm("llm:<task>" | "search" | "image" | "tts" |
  "music" | "stock", error_type, times)`
* `app.analytics.faults`, `app.trends.faults`
* retry taxonomy (`app/providers/errors.py`): `TIMEOUT`, `RATE_LIMIT`,
  `INVALID_OUTPUT` are retryable; `AUTH_ERROR`, `BUDGET_EXCEEDED` are not.

## Run

```bash
APP_ENV=test .venv/Scripts/python.exe -m pytest -p no:randomly -q \
  -m "failure or recovery" tests/phase9/
```

## Coverage & results — 2026-09-01

| scenario | §ref | where | result |
|---|---|---|---|
| LLM `TIMEOUT` ×2 then success | §23 | `test_failure_recovery.py` | retries, campaign SUCCESS |
| LLM `RATE_LIMIT` | §23 | `test_failure_recovery.py` | retries, SUCCESS |
| LLM `AUTH_ERROR` (non-retryable) | §23 | `test_failure_recovery.py` | surfaced, campaign not SUCCESS, no fake result |
| Invalid JSON from a model | §23 | `tests/agents/test_model_gateway.py` (gateway escalates) | escalates to next engine |
| Image / TTS provider failure → resume keeps prior assets | §24-§26 | `tests/media/test_failure_resume.py` | images kept, not regenerated on resume |
| Video scene-level failure | §25 | `tests/media/` + Smart-Rerender | scene-scoped, completed work retained |
| Search provider unavailable | §27 | `test_failure_recovery.py` | `InsufficientResearchError`, no Script, not SUCCESS |
| DB connection drop (`engine.dispose()`) | §28/§30 | `test_infra_and_ops.py` | `pool_pre_ping` reconnects transparently; workload still runs |
| Transaction failure mid-write | §29 | `test_infra_and_ops.py` | full rollback, no orphan campaign |
| Redis down | §32 | `test_infra_and_ops.py` | `readiness()` reports DOWN, no crash, campaigns still run inline |
| Worker crash mid-pipeline → restart resume | §33/§53 | `test_failure_recovery.py`, `tests/test_checkpoint_resume.py` | **0 duplicate AgentRuns**; completed nodes not re-billed |
| Two runners, same PublishJob | §34/§35 | `test_publishing_safety.py`, `test_infra_and_ops.py` | 1 remote post; idempotent skip on the loser |
| Cancel | §54 | `test_failure_recovery.py` | no new AgentRun / PublishJob after CANCELLED |
| Media budget guard blocks then allows | §41 | `tests/media/test_failure_resume.py` | scenes survive, resume completes |

## Recovery guarantees

* **Restart-resume never duplicates provider work.** The LangGraph Postgres
  checkpointer keys on `campaign_id` as `thread_id`; a resumed run replays only
  `snap.next` nodes. Verified: `AgentRun` counts for Research/Fact/Strategy are
  identical before and after a resume.
* **Idempotency for external effects.** `PublishJob.idempotency_key` +
  `remote_post_id` short-circuit; the mock platform's `_by_key` index means a
  double-fire yields one post. Retry after a timeout returns `idempotent_skip`.
* **Fail-safe on governance error.** A governance exception in the publish worker
  resolves to `HUMAN_REVIEW` / not-publishable, never PUBLISHED.
