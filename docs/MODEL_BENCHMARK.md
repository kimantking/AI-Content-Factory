# MODEL BENCHMARK — Phase 8

> Code: `backend/app/ai_router/benchmark.py`. API: `POST /api/models/benchmark`,
> `GET /api/models/performance`, `POST /api/models/performance/recompute`.

## Task set (spec §31)

A small fixed set built from OUR real tasks: `classification`, `simple_summary`,
`fact_extract`, `url_triage`, `creative_qa_basic`. Each has an expected key so
accuracy is measurable without a human.

## Metrics

Per task: `schema_valid` (parsed as a JSON object), `accurate` (expected key
present + non-empty), `latency_ms`, `cost_usd` + `cost_state`, `error`.
Rolled up: `schema_valid_rate`, `accuracy`, `avg_latency_ms`, `failure_rate`,
and a `verified` label: `LOCAL_VERIFIED` (ollama) / `CLOUD_VERIFIED` (real key) /
`MOCK_VERIFIED` (mock provider — still exercises the plumbing).

## Output

Writes `ModelPerformance` rows (`benchmark_state=BENCHMARKED`) that the Model
Router and the `/settings/local-ai` screen read back. A benchmark with few
samples still leaves routing policy unchanged until `MODEL_ROUTING_MIN_SAMPLE`
real observations accumulate (`MODEL_ROUTER.md` §telemetry).
