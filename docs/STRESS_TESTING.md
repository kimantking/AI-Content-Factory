# Stress Testing (Phase 9)

Model-router mixed load, local-AI concurrency, and overload behaviour. Mock +
local providers only.

## Run

```bash
APP_ENV=test .venv/Scripts/python.exe -m pytest -p no:randomly -q \
  tests/phase9/test_invariant_recheck.py tests/phase9/test_security_load.py \
  tests/agents/test_model_gateway.py tests/ai_router/
```

## Model Router under mixed load (§18-§20)

Covered by `tests/agents/test_model_gateway.py` +
`tests/ai_router/test_router.py` + the Phase 9 concurrent-campaign run
(`test_concurrent_load.py`), where a single 20-campaign burst issues
`research_summary` / `strategy` / `hook` / `final_script` tasks simultaneously:

* light/standard tasks routed to the local tier (or the mock stand-in when Ollama
  is not the pick); premium tasks (`strategy`/`hook`/`final_script`) routed to the
  premium tier — **not all work collapses onto one engine**;
* every routed call recorded a `ModelRoutingEvent`; tiers seen across a single
  campaign span `standard` + `premium`;
* `LOCAL_ONLY` (`allow_cloud_fallback=false`) + a dead local engine → **0 cloud
  calls**, controlled failure (verified in `test_invariant_recheck.py` and
  `test_model_gateway.py`).

## Local AI concurrency / overload (§19-§22)

* `local_model_max_concurrency` (default 2) + `local_model_timeout_seconds`
  (default 120) bound simultaneous Ollama requests; the router's bounded fallback
  chain (≤4) prevents unbounded retry when the local engine is slow.
* **Ollama down**: `OllamaLLMProvider.health()` returns a DOWN/degraded status and
  never raises through the app (`app/providers/ollama_llm.py`); with
  `allow_cloud_fallback=true` an allowed task falls back, with `LOCAL_ONLY` it is
  a clear failure — `test_model_gateway.py::test_local_only_never_calls_cloud`,
  `test_cloud_fallback_respects_setting`.
* **Ollama recovery**: `get_registry(refresh=True)` / `refresh_health()`
  re-probes and re-enables local routing; failed tasks follow the normal retry
  policy — `tests/ai_router/test_ollama.py`.

## Overload / backpressure (§12-§13)

* Autopilot production is gated by `queue_backpressure.production_allowed()` and
  the per-channel capacity planner (`autopilot/capacity.py`, AUDIT-P6-001) — an
  over-capacity run is HELD (`WAITING_FOR_CAPACITY` / `HOLD`), never a crash.
* The DB pool (`pool_size` + `max_overflow`) caps concurrent DB work; the Phase 9
  20-campaign burst stayed within it (high-water 11 checked out / 8 overflow).

## Direct provider bypass

`test_invariant_recheck.py::test_inv_direct_provider_bypass_zero` — still **0**
`get_llm_provider()` calls in `agents/nodes.py`, `agents/media_nodes.py`,
`autopilot/pipeline.py`.
