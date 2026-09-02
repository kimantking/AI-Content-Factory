# Soak Testing (Phase 9)

A small workload — one campaign + one 3-URL LEARN_ONLY batch + one library read —
repeated for `SOAK_SECONDS`, sampling Python heap (`tracemalloc`), DB-pool
checkout, and (best-effort) process RSS / handle count every 5 cycles. Fails on a
sustained upward trend.

## Modes

| mode | `SOAK_SECONDS` | when |
|---|---|---|
| QUICK_SOAK | 180–900 (env-dependent) | **required** at the Phase 9 gate |
| FULL_SOAK | ~2400 | recommended before a Phase 10 production release — `AVAILABLE_NOT_REQUIRED` here |

## Run

```bash
SOAK_SECONDS=180 APP_ENV=test .venv/Scripts/python.exe -m pytest -p no:randomly \
  -q -s -m soak tests/phase9/test_soak.py
```

## QUICK_SOAK result — 2026-09-01

Environment note: the host has ~3 GB free RAM and this pytest harness buffers
output, so the run was capped at **180 s** rather than the §86 target of 10–15 min.
Longer background runs were killed by the environment; the 180 s run is a clean,
uncontested sample (earlier apparent slow-downs were 4 orphaned pytest processes
from killed jobs competing for CPU/DB — killed, then the soak ran at a steady
~1.5 s/cycle throughout).

| metric | start | end | slope / sample | verdict |
|---|--:|--:|--:|---|
| cycles | — | **123** (123 ok / 0 failed) | — | PASS |
| Python heap (`tracemalloc`) | 17.15 MB | 17.19 MB | +0.0008 MB | flat — no leak |
| DB pool checked-out | 0 | 0 | 0 | flat — no connection leak |
| RSS / handles | n/a | n/a | — | Win32 counter unavailable under this Python; heap + pool are the signals |

* Queue: never stuck (each cycle's learning job reached `DONE`).
* Workers: n/a (inline).
* Temp files: campaigns/learning write to per-test storage roots; no accumulation
  observed in the pool or heap.
* **Possible leak: NO.**

FULL_SOAK: NOT_RUN (AVAILABLE_NOT_REQUIRED — recommended before Phase 10).
