# MODEL ROUTER + MODEL REGISTRY — Phase 8

> Code: `backend/app/ai_router/` (`registry.py`, `router.py`, `execute.py`,
> `pricing.py`, `telemetry.py`, `benchmark.py`). API: `/api/models*`,
> `/api/routing/telemetry`.

## Principle

The router chooses **which engine runs a task** — deterministic Python, local
Ollama, cheap cloud, or premium cloud — from **task fit + quality + cost +
latency + reliability + privacy**. Never price alone (spec §20). Deterministic
tasks never touch a model. `ALLOW_CLOUD_FALLBACK=false` removes every cloud model
from consideration.

## Model Registry (`registry.py`)

Entries carry: `provider`, `family`, `kind` (deterministic | local | cloud),
`enabled`, `health` (OK/DEGRADED/DOWN/UNKNOWN), `vision`, `tools`,
`context_tokens`, `latency_class`, `quality_class`, `pricing_state`,
`benchmark_state`. `refresh_health()` live-probes Ollama for local models and
enables cloud models only when a key is set (and not LOCAL_ONLY). Default set:
`python`, `gemma3:4b` (local/standard), `claude-haiku-4-5-*` (cloud/standard),
`claude-sonnet-5` (cloud/premium).

## Tiers (spec §19)

| tier | tasks (examples) | engine |
|---|---|---|
| `deterministic` | hash, dedup, similarity, sort, numeric, validation, cost_calc, fingerprint | **Python — no model call** |
| `local_light` | classification, tagging, url_triage, simple_summary, dataset_cleanup, topic_clustering, keyword_extract | local first, cloud only as fallback |
| `standard` | reference_analysis, research_summary, rewrite, creative_qa_basic, fact_extract, subtitle_polish, platform_adapt | local or cheap cloud (not premium first) |
| `premium` | strategy, hook, final_script, creative_direction, fact_conflict, critical_reasoning, prompt_distillation_final, retention_direction | premium cloud, then cheap cloud, then local |

`complexity=high` bumps one tier up (never past a deterministic floor). Quality
preset `fast` softens `premium → standard`; `max` never lifts a
hash/classification into a premium model.

## Agent default tier (`AGENT_TIER`, spec §22)

Research → standard · Fact Checker → deterministic (+escalation) · Data Curator /
Dataset Analyzer → local_light · Hook / Script / Story / Video / Retention
Directors → premium · Subtitle → local_light · Voice / Audio / B-roll / Graphics /
Thumbnail / Platform Adapter → standard · Prompt Distillation → local_light
(aggregate) with only a VALIDATED candidate going premium · Governance →
deterministic (rules first).

## `run_routed` (`execute.py`)

Resolves the decision to a provider, calls it, validates JSON, and:
- **escalates** to the next (better) engine on schema-invalid or `confidence<0.35`;
- **walks the fallback chain** on a provider `ProviderError`;
- honours **LOCAL_ONLY** — a cloud provider is never constructed;
- records one `ModelRoutingEvent` per attempt (telemetry never breaks the task).
No infinite escalation — the chain is bounded (≤4 engines).

## Routing telemetry + performance memory (spec §32, §33)

`ModelRoutingEvent`: agent/task/tier/model/provider, latency, tokens, estimated &
actual cost + state, schema_valid, quality_signal, success, fallback_used,
escalated. `recompute_performance()` rolls these into `ModelPerformance` per
`(model, task)`: schema_valid_rate, success_rate, avg_latency, avg_quality,
avg_cost, `strength` (STRONG/OK/WEAK/UNKNOWN). Strength stays **UNKNOWN** until
`MODEL_ROUTING_MIN_SAMPLE` (8) observations — the router does not flip policy on
n=1.

## Benchmark (`benchmark.py`, `MODEL_BENCHMARK.md`)

Scores a model on OUR task set (classification / summary / fact-extract /
url-triage / hook-eval). Writes `ModelPerformance` with
`benchmark_state=BENCHMARKED`. `verified` = `LOCAL_VERIFIED` / `CLOUD_VERIFIED` /
`MOCK_VERIFIED`.

## Completion-gate guarantees (tested)

- deterministic task → `python`, no model call;
- local_light task → local model, premium only in the fallback list;
- premium task → premium cloud when available, honest local fallback otherwise;
- LOCAL_ONLY + local down → clear failure, **zero cloud calls**;
- schema-invalid local output → escalates and succeeds on the next engine.
