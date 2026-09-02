# COST OPTIMIZATION — Phase 8

> Code: `backend/app/ai_router/cost.py`, `pricing.py`; `app/intel/engine.py`
> (cheap-first learning). API: `/api/cost/estimate`.

## Cost Estimator (spec §23)

`estimate_campaign_cost(selection, quality_preset, execution_mode, reference_count)`
returns per-category lines — **LLM / LLM_learning / Search / Image / Video / TTS /
Stock / Storage** — each with a `state`:

| state | meaning |
|---|---|
| `KNOWN` | verified price (local = real $0) |
| `ESTIMATED` | public list price, approximate — operators verify before enabling a paid provider |
| `UNKNOWN` | no verified price — shown as "확인 불가", **never a fabricated number** |

Media providers are MOCK, so Image/Video/TTS/Stock are `UNKNOWN`. The structural
counts (content pieces / platform variants / publish jobs) are always exact.

## Local cost wording (spec §24)

Local (Ollama) API cost is a real `0`, but compute is not free. The UI shows
**"LOCAL PROCESSING · API ₩0"** and the estimate carries `local_processing: true`,
never "무료".

## Shared assets counted once (spec §25)

The master script and master video/thumbnail are counted once; only per-platform
adaptation scales with the number of selected media platforms. Changing the SNS
selection recomputes the estimate (`/api/cost/estimate` is called on every change
in `/create`). A DISABLED platform adds zero platform-specific cost.

## Quality routing (spec §26)

`fast` → local/cheap first · `balanced` → local + cloud · `high` → cloud standard
+ selective premium · `max` → wider premium — **but even `max` never sends
hash/classification to a premium model** (`ModelRouter._tier_for`).

## Budget-aware routing (spec §27)

`budget_state ∈ {ok, tight, critical}`. Under pressure the router prefers local,
drops premium (unless the tier demands it), and the pipeline reduces candidate
count / AI-video ratio and increases asset reuse + cache. **Fact safety,
governance and security are never bypassed.**

## Cheap-first learning (spec §28-§30)

`app/intel/engine.run_learning_job` already does: Stage-1 metadata/hash/dedup
(deterministic), Stage-2 classification/basic summary (local), Stage-3
quality/relevance, Stage-4 deep analysis on only the top-K
(`learning_deep_analysis_top_k`, default 20). Video references are analysed from a
caller-supplied structured profile (transcript / scene metadata / keyframes), not
the whole video. Prompt Distillation aggregates many references first; only a
sufficiently-evidenced candidate is considered for a higher-cost pass.
