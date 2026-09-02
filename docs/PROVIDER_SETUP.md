# Provider Setup (Phase 10 §5-§9)

Status vocabulary: `CODE_READY · TESTED · MOCK_VERIFIED · LOCAL_VERIFIED ·
CREDENTIAL_READY · PRODUCTION_VERIFIED · NEEDS_CREDENTIALS`.
**No provider is PRODUCTION_VERIFIED without a real credential + a real call.**

| Kind | Provider | Status | To enable |
|---|---|---|---|
| Text AI | Anthropic (`app/providers/anthropic_llm.py`) | CODE_READY + MOCK_VERIFIED | set `ANTHROPIC_API_KEY`; verify pricing in `app/ai_router/pricing.py`; then a small controlled probe |
| Text AI | Ollama `gemma3:4b` (`app/providers/ollama_llm.py`) | **LOCAL_VERIFIED** | `ollama serve` + `ollama pull gemma3:4b`; `OLLAMA_ENABLED=true` |
| Search | Tavily (`app/providers/tavily_search.py`) | CODE_READY + MOCK_VERIFIED | set `TAVILY_API_KEY` |
| Image | (mock only) | CODE_READY (abstraction) | wire a real adapter behind `providers/media/registry.py`; then `NEEDS_CREDENTIALS` |
| Video | (mock only / Image-Motion fallback) | CODE_READY | as image |
| Voice/TTS | (mock only) | CODE_READY | as image; `edge-tts` is dev/test only, never production default |

## Routing (§7) — `app/ai_router/router.py`
Light tasks (classification / tagging / basic extraction / simple summary /
dataset cleanup / reference triage) → **local preferred**. Strategy / Hook /
Final Script / Creative Direction / complex fact-conflict → policy-driven
Standard/Premium. **No task is forced onto Gemma.**
`Agent → PromptComposer → ModelExecutionGateway → ModelRouter → Provider`;
direct provider bypass = 0 (static guard `tests/agents/test_model_gateway.py`,
`tests/phase9/test_invariant_recheck.py`).

## LOCAL_ONLY / fallback (§8)
`ALLOW_CLOUD_FALLBACK=false` → a local failure never becomes a cloud call
(`LOCAL_ONLY` invariant). `=true` → only allowed tasks fall back.
`GLOBAL_PAID_PROVIDER_PAUSE` → 0 cloud/paid calls, local Ollama still runs.

## Pricing registry (§9) — `app/ai_router/pricing.py`
`(provider, model) → (input $/Mtok, output $/Mtok, state)` where state ∈
`KNOWN | ESTIMATED | UNKNOWN`. Unknown pricing is surfaced as `UNKNOWN`, never 0.


## Phase 11 — Google AI + ElevenLabs (added 2026-09-01)

Both adapters use **stdlib `urllib`** (same approach as `OllamaLLMProvider`) —
**0 new dependencies**. Model names live only in `app/config.py`
(`google_image_model`, `google_video_model`, `elevenlabs_model`), never hardcoded
in adapter code. Keys are **backend only** — no `NEXT_PUBLIC_*`, never logged,
redacted everywhere (`app/ops/redaction.py`).

### Google AI
* Canonical env: **`GOOGLE_API_KEY`** (falls back to `IMAGE_API_KEY`/`VIDEO_API_KEY`).
* `IMAGE_PROVIDER=google` → `GoogleImageProvider` (Imagen `:predict`; aspect ratio
  mapped from width/height to the supported set).
* `VIDEO_PROVIDER=google` → `GoogleVideoProvider` (Veo `:predictLongRunning` →
  bounded synchronous poll of the operation → retrieve). Fits the existing
  `VideoProvider` protocol and the worker/checkpointer/idempotency model
  unchanged; `get_video_provider()` returns it. **The render pipeline still
  downgrades AI_VIDEO scenes to image-motion until `MAX_AI_VIDEO_RATIO>0` and a
  media-node call site are enabled** — the adapter is connected, the pipeline
  invocation is a deliberate opt-in.
* Read-only health probe: `GET /v1beta/models` (list, free — never a generation).
* Cost: `MediaResult.cost = 0.0`, `meta.cost_state = "UNKNOWN"` (Google media
  pricing is not verified — never fabricated).

### ElevenLabs
* Canonical env: **`ELEVENLABS_API_KEY`** (falls back to `TTS_API_KEY`).
* `TTS_PROVIDER=elevenlabs` → `ElevenLabsTTSProvider` (`/v1/text-to-speech/{voice}/
  with-timestamps`, `output_format=pcm_24000` wrapped in a 24 kHz WAV so the
  timing/subtitle/render pipeline is unchanged; duration = last alignment
  end-time, not estimated).
* `ELEVENLABS_VOICE_ID` is **required** — no invented default voice. Voice
  cloning is not implemented; consent/governance is not bypassed.
* Read-only health probe: `GET /v1/voices`.
* Cost: `cost = 0.0`, `meta.cost_state = "UNKNOWN"`.

### Normalised errors (AI Support Snapshot)
`GOOGLE_NOT_CONFIGURED / GOOGLE_AUTH_FAILED / GOOGLE_RATE_LIMITED /
GOOGLE_PROVIDER_ERROR` and `ELEVENLABS_*` — each with a one-line suggested action
(`app/support/errors.py`). The `error_type` stays a standard retry-taxonomy value
(`AUTH_ERROR` / `RATE_LIMIT` / `TIMEOUT` / `PROVIDER_ERROR`) so retry behaviour is
unchanged; the vendor code rides along as `provider_code`.

### Status
`GET /api/providers` (and the AI Support Snapshot `system.cloud_providers.providers`)
report `CONNECTED / NOT_CONFIGURED / DEGRADED / ERROR` for anthropic / tavily /
google / elevenlabs / ollama. Never returns a key value.
`GLOBAL_PAID_PROVIDER_PAUSE` also falls real media providers back to mock.
