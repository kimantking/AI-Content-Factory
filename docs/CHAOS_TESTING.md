# Chaos Testing (Phase 9 §100-§101)

Controlled fault injection only — never against real user data. Each scenario has
an expected state and a verified recovery.

| # | scenario | injection | expected | recovery | verified in |
|---|---|---|---|---|---|
| C1 | Worker dies during render | `faults.arm("tts"/"image", AUTH_ERROR)` then resume | hard stop at the failing node; prior assets kept | `run_media_pipeline(resume=True)` regenerates only the missing node | `tests/media/test_failure_resume.py` |
| C2 | Redis restart during queue | `check_redis → DOWN` | `readiness()` DOWN, app + inline campaigns unaffected | Redis reconnect on next probe | `tests/phase9/test_infra_and_ops.py` |
| C3 | Ollama down during local routing | `_provider_for(ollama)` raises | LOCAL_ONLY → 0 cloud, controlled failure; else allowed fallback | `refresh_health()` re-enables local | `tests/agents/test_model_gateway.py`, `tests/phase9/test_invariant_recheck.py` |
| C4 | Cloud provider timeout | `faults.arm("llm:*", TIMEOUT)` | retry w/ backoff; AUTH_ERROR not retried | 3rd attempt succeeds / honest failure | `tests/phase9/test_failure_recovery.py` |
| C5 | Storage failure after render | missing / partial asset path | `MISSING_ASSET` in the library card, page does not 500 | re-render on demand | `tests/library/` + `_file_exists` guard in `service.py` |
| C6 | SNS publish timeout | double-fire same `PublishJob` | 1 remote post (idempotency_key + remote_post_id) | `idempotent_skip` on the retry | `tests/phase9/test_publishing_safety.py` |
| C7 | Budget reaches limit mid-run | `campaign_budget_usd` below spent | `check_budget` raises; no new paid call; completed assets kept | resume after raising the limit | `tests/phase9/test_invariant_recheck.py`, `tests/media/test_failure_resume.py` |
| C8 | Governance flips to BLOCK after queue | expired `RightsLedger` + scheduled publish | worker re-checks rights before the API call → 0 remote | fix rights / manual review | `tests/phase9/test_publishing_safety.py` |
| C9 | DB connection drop | `engine.dispose()` | `pool_pre_ping` transparent reconnect | workload continues | `tests/phase9/test_infra_and_ops.py` |
| C10 | Worker crash mid-pipeline | `faults.arm` after research/fact/strategy, then resume | stopped at `snap.next`; **0 duplicate AgentRuns** | checkpoint resume | `tests/phase9/test_failure_recovery.py`, `tests/test_checkpoint_resume.py` |

**§101** — no random destructive chaos was run against real data; all injection is
through `app.providers.faults` / controlled connection disposal in the test DB.
