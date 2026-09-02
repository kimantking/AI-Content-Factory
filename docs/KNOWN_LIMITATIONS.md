# Known Limitations — v1.0.0 (Phase 10)

Not defects. Real credentials / infrastructure / a human-approved pilot are still
required before unrestricted production.

## NEEDS_CREDENTIALS
- Paid AI providers: Anthropic (`ANTHROPIC_API_KEY`), Tavily (`TAVILY_API_KEY`).
- **Google AI** (image = Imagen, video = Veo): adapters wired
  (`GOOGLE_API_KEY` + `IMAGE_PROVIDER=google` / `VIDEO_PROVIDER=google`), tested
  with mocked HTTP — **no paid generation performed**. The Veo adapter is
  protocol-complete and registry-selected, but the render pipeline still
  downgrades AI_VIDEO scenes to image-motion until `MAX_AI_VIDEO_RATIO>0` and a
  media-node call site are turned on.
- **ElevenLabs** voice/TTS: adapter wired (`ELEVENLABS_API_KEY` +
  `TTS_PROVIDER=elevenlabs` + `ELEVENLABS_VOICE_ID`), tested with mocked HTTP —
  **no paid synthesis performed**.
- Google/ElevenLabs media pricing is **UNKNOWN** (not verified) — cost is never
  fabricated; the estimator reports UNKNOWN.
- SNS: YouTube, TikTok, Instagram, Facebook, Threads, X, Pinterest, LinkedIn —
  OAuth + (most) app review + (some) account-type requirements. Naver Blog =
  MANUAL_ONLY, Naver Clip = NOT_SUPPORTED.
- Platform analytics scopes; monetisation / revenue API permissions.

## NEEDS_PRODUCTION_ENVIRONMENT
- Real domain + TLS + reverse proxy (HTTP-only is not production).
- Off-site backup target; WAL archiving / PITR.
- External alert delivery (email / Slack / PagerDuty) — in-app notifier only.
- A real Celery worker pool under sustained load (Phase 9 ran inline).

## Product limitations
- Browser E2E is HTTP-level; rendered-browser Playwright needs a new dev dep
  (D67 approval) + is not global-installed. `tsc` + `next build` are the frontend
  gate. (P9-L-001)
- FULL_SOAK not run (QUICK_SOAK passed); recommended before a large pilot. Soak
  RSS/handle counters unavailable under the MSYS2 Python — heap + DB-pool are the
  leak signals. (P9-L-002)
- pgvector extension not installed; the app uses a deterministic JSON-vector
  embedding fallback (D61). Non-blocking.
- Media providers are mock-only → media cost is `UNKNOWN`, never fabricated.
- Autopilot capacity-planner and NL-edit have backend + API; the scene-editor
  *panel* UI and a capacity widget are LOW (deferred).
- `GLOBAL_PAID_PROVIDER_PAUSE` currently gates the cloud LLM path; media paid
  providers are mock-only so the gate there is a no-op until a real adapter lands.

## First pilot constraint
Real publish = **NEEDS_USER_APPROVAL**. Start 1 content × 1 platform (private /
unlisted where supported). No mass automation on day one.
