# TEST MODES / TIERS — Phase 8

> `backend/pytest.ini` markers. Directory layout is the primary selector; markers
> add cross-cutting selection. Existing test semantics are unchanged.

## Markers

| marker | meaning |
|---|---|
| `fast` | quick unit-level checks, safe to run continuously during development |
| `integration` | end-to-end; shells out to ffmpeg / builds full campaigns (slow) |
| `media` | exercises the media / render pipeline |
| `governance` | Phase 7 content-governance suite |
| `intel` | Cross-Phase Intelligence Upgrade suite |
| `production` | needs real infrastructure / credentials (skipped by default) |
| `full` | only at a completion gate |

## Recommended flow (spec §96)

1. **targeted** — the touched dir(s), e.g. `pytest tests/ai_router tests/library`
2. **affected integration** — e.g. `pytest tests/intel tests/publishing -m "not integration"` then the marked ones
3. **frontend** — `npx tsc --noEmit && npm run build`
4. **E2E** — `pytest tests/test_phase8_e2e.py tests/intel/test_e2e_intel.py`
5. **full** — only at the completion gate: whole suite, 0 failed required.

Because a single 20-minute background run was being killed mid-way in this
environment, the full regression is run in two halves (fast dirs, then
ops/publishing/video) and the results aggregated — every collected test still
executes.

## Local Ollama tests

`tests/ai_router/test_ollama.py` auto-skips the real-inference cases when Ollama
is unreachable (`_ollama_up()`), and always runs the graceful-degradation cases.
When Ollama + `gemma3:4b` are present the result is **LOCAL_VERIFIED**.
