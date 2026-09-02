# Load Testing (Phase 9)

Concurrent-campaign and learning-batch load. All runs use **mock providers + local
Ollama + deterministic fixtures** — no paid API calls (§7).

## Run

```bash
cd backend
APP_ENV=test .venv/Scripts/python.exe -m pytest -p no:randomly -q -s -m load tests/phase9/
```

Individual tiers:

| file | scenario | §ref |
|---|---|---|
| `tests/phase9/test_concurrent_load.py` | 5 / 10 / 20 concurrent Phase 1-A pipelines | §10-§13 |
| `tests/phase9/test_learning_load.py` | LEARN_ONLY batch 10 / 50 / 100 references | §14-§17 |
| `tests/phase9/test_content_library_scale.py` | 1000 campaigns / 3200 platform contents | §55-§58 |

## What it measures (recorded per run)

`started_at / finished_at / duration / items / ok / failed`, plus the SQLAlchemy
pool high-water mark (`checked_out`, `overflow`) and per-campaign latency p50/max.

## Results — 2026-09-01 (Windows, PG 16 :5433, mock providers, inline workers)

### Concurrent campaigns

| n | workers | ok | failed | wall | p50 lat | max lat | pool checkout HW | overflow HW | corruption |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--|
| 5 | 5 | 5 | 0 | 0.9 s | 0.63 s | 0.66 s | 4 | 4 | none |
| 10 | 8 | 10 | 0 | 1.28 s | 0.98 s | 1.05 s | 10 | 8 | none |
| 20 | 8 | 20 | 0 | 2.39 s | 0.93 s | 1.09 s | 11 | 8 | none |

Pool: base size 5 + overflow (max 10). At 20 concurrent the high-water was 11
checked out / 8 overflow — **bounded, no `pool_timeout`, no exhaustion**. Every
campaign completed and passed the internal-consistency check (Script row +
knowledge_pack + SUCCESS status all agree). No race / no partial state.

### Learning batch (LEARN_ONLY)

| n refs | duration | analyses rows | deep-analysed refs | production footprint |
|--:|--:|--:|--:|---|
| 10 | 0.32 s | 21 | 7 | campaigns 0 / assets 0 / media 0 / publish 0 |
| 50 | 0.48 s | 45 | 15 | campaigns 0 / assets 0 / media 0 / publish 0 |
| 100 | 0.87 s | 65 | **20 (== `learning_deep_analysis_top_k`)** | campaigns 0 / assets 0 / media 0 / publish 0 |

**Cheap-first confirmed:** at 100 references, deep analysis is capped at the
top-20 by quality; the analyzers are deterministic — **0 premium LLM calls for
the whole batch**. Dedup (exact / canonical / same-hash) collapses at add time and
marks content duplicates; dataset rows stay bounded.

### Content Library at scale

1000 campaigns + 3200 platform contents, legacy + current mixed:

| operation | before fix | after fix (P9-001) |
|---|--:|--:|
| `GET /api/library` page 1 (page_size 30) | 9.3 s | **0.25 s** |
| `GET /api/library` page 10 / 33 | ~9 s | 0.22 s |
| `GET /api/library?q=…` | ~9 s | 0.23 s |

**Defect P9-001** (fixed): `list_content` enriched **every** matching campaign
before slicing the page — O(N) child-row queries regardless of page. Fixed with a
DB-level `OFFSET/LIMIT` fast path (`_card()` helper) for the common case (no
python-only filter, no metric sort); the full-scan path is kept only for
`platform`/`content_type`/`governance`/`publish_state` filters and
`views`/`revenue`/`profit`/`performance` sorts. Legacy-mix and search stay bounded
and correct.
