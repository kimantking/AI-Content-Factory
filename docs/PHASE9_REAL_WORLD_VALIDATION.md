# Phase 9 — Real-World Validation (load / stress / soak / failure / recovery / browser E2E / ops hardening)

Not a new product. Phase 1–8 is `PHASE_1_8_FUNCTIONAL_BASELINE_LOCKED`. Phase 9
asks: *does it hold up under concurrency, time, and failure — without breaking any
invariant?* Real execution / measurement / fault injection / recovery, not prose.

Phase 10 is NOT started here.

---

## 2. Baseline freeze (recorded 2026-09-01, before Phase 9 work)

| item | value |
|---|---|
| Migration head | `0011_medium_repair` (single head, chain 0001→0011, no branches) |
| ORM tables in DB | 102 (`information_schema`), `alembic_version = 0011_medium_repair` |
| Backend test count | **486** collected (`pytest --co`) |
| Frontend | Next.js 15 / React 19; `tsc --noEmit` + `next build` — see §116 result |
| Critical invariants | 12, all holding (audit + D94/D95 evidence) |
| Verdict entering Phase 9 | **B** — functionally complete, production verification pending |

### Service versions / pre-flight (§5, §6)

| component | detail | state |
|---|---|---|
| Backend (FastAPI) | Python 3.12.10, `app.main:app` imports clean | READY |
| PostgreSQL | 16.15 (Debian), container `ai-content-factory-postgres-1` healthy 35 h, port 5433 | READY |
| pgvector | extension **not installed**; app uses the deterministic JSON-vector embedding fallback (D61 — real embeddings deferred) | NOT_AVAILABLE (non-blocking) |
| Redis | `redis://localhost:6379/0`, PING ok, container healthy 35 h | READY |
| Workers | Celery/Redis available; tests + Phase 9 load run **inline** (`run_inline=True`) — a real worker pool is a NEEDS_PRODUCTION_ENVIRONMENT concern | READY (inline) |
| FFmpeg | `imageio-ffmpeg` bundled `ffmpeg-win64-v4.2.2` (no system ffmpeg on PATH) | READY |
| Storage | local filesystem, `C:` 738 GB free (21 % used) | READY |
| Ollama | 0.33.2 at `http://localhost:11434` | READY |
| gemma3:4b | present in `/api/tags`; real JSON inference verified | LOCAL_VERIFIED |
| Docker | `postgres`, `redis`, `m1-postgres` containers healthy | READY |
| Host memory | 16.2 GB total, ~3.3 GB free at preflight — **tight**; highest load/soak tiers run DEGRADED / bounded | DEGRADED (headroom) |
| Ports | 5433 (pg), 6379 (redis), 11434 (ollama) listening | READY |

**Paid-surprise guard (§7):** all Phase 9 load/stress/soak runs use Mock providers +
local Ollama + deterministic fixtures. No paid provider is called in bulk. No
`NEEDS_CREDENTIALS` item is marked VERIFIED.

---

## 3. Test tiers

`tests/phase9/` — pytest markers `phase9` + one of `smoke` / `load` / `failure` /
`recovery` / `soak` / `browser_e2e`. FULL regression runs once, last.

Run recipes are in `docs/LOAD_TESTING.md`, `STRESS_TESTING.md`, `SOAK_TESTING.md`,
`FAILURE_RECOVERY.md`, `CHAOS_TESTING.md`, `BROWSER_E2E.md`.

## Results — 2026-09-01

New suite `tests/phase9/` = **59 tests** (58 + 1 soak), **0 failed**. Detail per
tier in `LOAD_TESTING.md`, `STRESS_TESTING.md`, `SOAK_TESTING.md`,
`FAILURE_RECOVERY.md`, `CHAOS_TESTING.md`, `BROWSER_E2E.md`,
`PERFORMANCE_BASELINE.md`, `OPERATIONS_RUNBOOK.md`.

| tier | tests | result |
|---|--:|---|
| Smoke (`test_smoke.py`) | 3 | PASS — full-stack create→library, governance/dry-run, SNS-OFF = 0 gen/0 publish |
| Invariant recheck (`test_invariant_recheck.py`) | 12 | PASS — all 12 Phase 1-8 invariants + Ollama LOCAL_VERIFIED |
| Concurrent load (`test_concurrent_load.py`) | 4 | PASS — 5/10/20 concurrent, 0 corruption, pool bounded (11/8 HW) |
| Learning load (`test_learning_load.py`) | 5 | PASS — LEARN_ONLY 10/50/100 → 0 production; cheap-first (deep ≤ top-20); dedup bounded |
| Failure/recovery (`test_failure_recovery.py`) | 6 | PASS — LLM timeout/429/auth taxonomy, search honest-fail, restart-resume 0 dup, cancel |
| Publishing safety (`test_publishing_safety.py`) | 3 | PASS — concurrent double-fire → 1 remote post; retry → idempotent_skip; rights-expiry after queue → 0 remote |
| Infra/ops (`test_infra_and_ops.py`) | 7 | PASS — DB reconnect, rollback no-orphan, Redis-down graceful, same-job no double-effect, multi-workspace no leak, autopilot dry-run 0 production + no dup cycles |
| Security load (`test_security_load.py`) | 8 | PASS — poisoned ref in a batch = 0 execution, SSRF/redirect-SSRF blocked end-to-end, internal Ollama path unaffected |
| Content Library scale (`test_content_library_scale.py`) | 4 | PASS — 1000 campaigns / 3200 contents, pagination bounded (**P9-001 fixed: 9.3 s → 0.25 s**), legacy mix, search/filter |
| E2E journeys (`test_e2e_journeys.py`) | 6 | PASS — HTTP-level beginner / learning / edit / platform-add / review / mobile |
| QUICK_SOAK (`test_soak.py`) | 1 | PASS — 123 cycles / 180 s, heap flat (+0.0008 MB/sample), pool flat at 0, 0 failed |

**Full regression (baseline 486 + 59 Phase 9 = 545): 545 passed / 0 failed / 0
errors** (4 batches + phase9 + soak).

### Defect found & fixed

* **P9-001** (MEDIUM, fixed) — `library.service.list_content` enriched *every*
  matching campaign before slicing the page → O(N) child queries, 9.3 s at 1000
  campaigns. Fixed with a DB-level `OFFSET/LIMIT` fast path (`_card()` helper);
  full-scan kept only for python-only filters / metric sorts. Now 0.25 s, flat
  across pages. Test: `tests/phase9/test_content_library_scale.py` (4).

### Not run / environment-limited

* Rendered-browser E2E (Playwright) — no runner installed; new dev dep needs D67
  approval, global install disallowed. HTTP-level journeys + `tsc` + `next build`
  stand in. `AVAILABLE_NOT_REQUIRED`.
* FULL_SOAK — `AVAILABLE_NOT_REQUIRED` (recommended before Phase 10).
* Off-site backup / WAL / PITR / external monitoring / real domain+TLS / SNS OAuth
  / paid provider keys / analytics scopes / revenue APIs —
  `NEEDS_PRODUCTION_ENVIRONMENT` / `NEEDS_CREDENTIALS`, unchanged.
