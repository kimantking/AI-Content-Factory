# Performance Baseline (Phase 9 §102-§104)

Measured 2026-09-01 on the dev host (Windows, PG 16 @ :5433 in Docker, Ollama
0.33.2 local, **mock content/media providers**, inline workers). Median of 3–4
runs unless noted.

**These are local/dev measurements, not an SLA.** §103 — no number here is a
guaranteed service level. Real-provider latency (Anthropic, Tavily, media, SNS)
is unmeasured and stays `NEEDS_CREDENTIALS`.

| operation | scale | median | min | max | note |
|---|---|--:|--:|--:|---|
| Quick Create — full Phase 1-A pipeline (research→fact→strategy→hook→script→QA) | 1 campaign, mock LLM/search | **904 ms** | 899 | 1063 | dominated by 6 mock LLM calls + DB writes |
| Local LLM call — `gemma3:4b` via Ollama | 1 classification call | **2234 ms** | 2229 | 12736 | first (cold) call 12.7 s; warm ~2.2 s |
| Learning batch — LEARN_ONLY | 10 refs | **130 ms** | 114 | 328 | deterministic fetch/extract/analyze |
| Learning batch — LEARN_ONLY | 50 refs | **458 ms** | 439 | 476 | ~9 ms/ref; deep analysis capped at top-20 |
| Content Library page — `GET /api/library` (page 1, size 30) | 1000 campaigns / 3200 contents | **297 ms** | 252 | 321 | after P9-001 fix (was 9.3 s) |
| Content Library page — deep page (10 / 33) | 1000 campaigns | ~225 ms | — | — | flat across pages (DB `OFFSET/LIMIT`) |
| Library search — `?q=` | 1000 campaigns | **272 ms** | 266 | 292 | topic + script-body ILIKE |
| Library stats — `GET /api/library/stats` | 1000 campaigns | **23 ms** | 20 | 25 | aggregate query |
| Concurrent campaigns — 20 in flight (8 workers) | mock | wall **2.39 s**, p50 0.93 s / max 1.09 s | — | — | pool high-water 11/8, no exhaustion |

## Regression watch (§104)

* **P9-001** — library pagination was O(N) (9.3 s @ 1000 campaigns). Fixed this
  phase (DB-level pagination fast path). Now 0.3 s, flat.
* No other clear performance regression observed. Micro-optimisation (batching the
  per-card child queries into `IN (…)` loads, a render-time budget) is deferred to
  post-Phase-10.

## Cold-start / first-call notes

* First `gemma3:4b` inference after Ollama idle: ~12.7 s (model load). Warm: ~2.2 s.
  The Model Router's local-tier timeout (`local_model_timeout_seconds=120`)
  absorbs this; production should pre-warm.
* `alembic upgrade head` on backend boot: sub-second (11 migrations, additive).
