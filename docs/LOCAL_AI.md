# LOCAL AI (Ollama) — Phase 8

> Code: `backend/app/providers/ollama_llm.py`, `app/ai_router/registry.py`.
> API: `/api/local-ai/status`, `/api/local-ai/ping`. UI: `/settings/local-ai`.

## What it is

`OllamaLLMProvider` implements the same `LLMProvider` protocol (`.complete`) as the
cloud adapters, talking to the Ollama REST API over **stdlib urllib** — no `ollama`
python package dependency (spec §14). Plus `health()` / `list_models()` /
`has_model()` / `ping_inference()` for the Model Registry and the settings screen.

## Verified locally (this environment)

- Ollama 0.33.2 reachable at `http://localhost:11434`.
- `gemma3:4b` (4.3B, Q4_K_M, ~3.3 GB) present; `capabilities: ["completion"]`.
- `/api/chat` with `format: "json"` returns a valid JSON object; a tiny classify
  prompt round-trips. → **LOCAL_VERIFIED** (`tests/ai_router/test_ollama.py`).

## Config (`app/config.py` / `.env.example`)

| key | default | meaning |
|---|---|---|
| `OLLAMA_ENABLED` | `false` (`true` in `.env.example`) | use the local provider at all |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint (trusted internal, see below) |
| `OLLAMA_DEFAULT_MODEL` | `gemma3:4b` | default local model |
| `ALLOW_CLOUD_FALLBACK` | `true` | `false` ⇒ **LOCAL_ONLY**: the router never selects or calls a cloud model |
| `LOCAL_MODEL_MAX_CONCURRENCY` | `2` | advisory cap for local inference |
| `LOCAL_MODEL_TIMEOUT_SECONDS` | `120` | per-call timeout → normalized `TIMEOUT` error |

## Failure handling (spec §16)

- `health()` never raises — returns `{status: CONNECTED|DEGRADED|NOT_RUNNING, ...}`.
- `complete()` raises a **normalized** `ProviderError` (`TIMEOUT` / `INVALID_OUTPUT`
  / `PROVIDER_ERROR`) — the Model Router walks its fallback chain.
- Ollama being down **never crashes the app**. `/api/local-ai/status` returns
  `200` with `status: NOT_RUNNING`; the registry marks local models `DOWN`.
- With `ALLOW_CLOUD_FALLBACK=false` and the local model down, a task fails with a
  clear error — it does **not** silently call a cloud model.

## Model download

Models (multiple GB) are **never** auto-pulled. The settings screen shows the
installed set and the "연결 확인 / 모델 확인 / 벤치마크" buttons only.

## SSRF vs the local endpoint (spec §78)

The configured Ollama endpoint is a **trusted internal provider config**, handled
separately from user-submitted URLs. A user pasting `http://localhost:11434` into
a *reference URL* field is still blocked by `app.intel.url_security` (localhost /
private IPs stay blocked for user input). The two paths never share trust.
