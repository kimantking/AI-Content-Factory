# OPEN SOURCE COMPONENTS

GitHub research for the Natural Content Engine (Design Amendment §1–2, §39).
**No repository is copied.** We reuse permissively-licensed libraries as
dependencies and reimplement *algorithm ideas* from the rest. Machine-readable
copy: `backend/app/opensource/registry.json` (served at `GET /api/open-source-components`).
Reviewed 2026-08-31.

| Repo | Feature we want | License | Usage | Commercial | Decision |
|---|---|---|---|---|---|
| [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | topic→copy pipeline, material search, subtitle/BGM, task mgmt, provider abstraction, web UI | MIT | ALGORITHM_REFERENCE | Clear | Study pipeline & provider-abstraction patterns; take the good parts, don't clone. |
| [m-bain/whisperX](https://github.com/m-bain/whisperX) | word-level timestamps, forced alignment, sentence boundaries | BSD-2-Clause (older docs say BSD-4) | DIRECT_DEPENDENCY | Clear | Phase 1-B: optional dep behind `AlignmentProvider`; system must not die if absent. Confirm BSD-2 at pin time. |
| [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor) | silence detection, dead-space removal, audio-based cutting, cut margins | Unlicense (public domain) | ALGORITHM_REFERENCE | Clear | Phase 1-B: reimplement silence + margin (80–350 ms) + pause-typing ideas in our Edit Engine; keep natural pauses. |
| [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | shot cut / transition detection in existing footage | BSD-3-Clause | DIRECT_DEPENDENCY | Clear | Phase 1-B: use to avoid inserting cuts across existing shot boundaries. Attribution in NOTICE. |
| [remotion-dev/remotion](https://github.com/remotion-dev/remotion) | programmatic React video rendering | Remotion License (source-available) | OPTIONAL_TOOL | **REVIEW REQUIRED** | Free for individuals / for-profit orgs **≤ 3 employees**. 4+ employees ⇒ paid Company License ($25/seat/mo Creators; $0.01/render Automators, $100/mo min; Enterprise $500/mo min). Decide **FFmpeg-only vs Remotion** before Phase 1-B rendering. |
| [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) | image/video upscaling, artifact cleanup | BSD-3-Clause (code) | OPTIONAL_TOOL | **REVIEW REQUIRED** | Phase 1-B, quality-gated (only below a quality score). Verify the **pretrained-weight** provenance/terms before commercial use. |
| [hzwer/ECCV2022-RIFE](https://github.com/hzwer/ECCV2022-RIFE) | frame interpolation for low-FPS generated clips | MIT (code) | OPTIONAL_TOOL | **REVIEW REQUIRED** | Phase 1-B, optional, QA-before/after (revert if not improved). README historically limits some **model weights** to non-commercial — confirm weight license before commercial use. |
| [blader/humanizer](https://github.com/blader/humanizer) | removes signs of AI-generated writing (agent skill) | MIT | REFERENCE_IMPLEMENTATION | Clear | Analyse the *tell list* / approach for our Natural Writing Engine. **Do not copy its prompts verbatim** (Amendment §4). |
| [rany2/edge-tts](https://github.com/rany2/edge-tts) | free MS Edge read-aloud TTS | LGPL-3.0 | OPTIONAL_TOOL | **REVIEW REQUIRED** | LGPL code is fine, but it hits Microsoft's online TTS with no Azure subscription — commercial use may breach Microsoft ToS. **Dev/test `TTSProvider` candidate only, never the production default** (Amendment §16). |

## Phase 4 research (trend detection / clustering / scoring)
Searched: *trend detection python*, *topic clustering embeddings*, *news trend
detection*, *multi armed bandit python*, *recommendation scoring*, *time series
anomaly detection*. Findings: `river` (online ML / bandits, BSD-3), `ruptures` /
`adtk` (change-point & anomaly, BSD/MPL), `sentence-transformers` (Apache-2.0,
heavy torch dep). **Decision: no new dependency.** The Opportunity Engine's
clustering, velocity/acceleration, anomaly and exploration logic are implemented
from first principles with stdlib + the existing cheap hashing embedding
(`app/analytics/embedding.py`). Revisit `sentence-transformers` only when a real
`EmbeddingProvider` is justified; revisit `river` if we move to true bandit
allocation (Phase 4 uses a simple, labelled exploration ratio instead).

## Phase 2 dependency
| Package | Feature | License | Usage | Notes |
|---|---|---|---|---|
| [`cryptography`](https://github.com/pyca/cryptography) (pyca) | Fernet symmetric encryption for OAuth token storage | Apache-2.0 / BSD-3 | DIRECT_DEPENDENCY | Standard, actively maintained. Master key from `ACF_MASTER_KEY`, never in DB. |

## Phase 5 research (production / security / backup / monitoring)
Searched: *prometheus python client*, *opentelemetry python*, *sentry sdk*,
*fastapi rate limit*, *SSRF protection python*, *postgres backup tool*,
*pgbackrest vs barman*, *caddy vs nginx vs traefik*, *loki promtail*,
*python circuit breaker*. Reviewed README / LICENSE / the one relevant module of
each — no repo cloned.

| Component | Feature we want | License | Decision |
|---|---|---|---|
| [`prometheus_client`](https://github.com/prometheus/client_python) | metrics registry + text exposition | Apache-2.0 | **NOT adopted.** `app/ops/metrics.py` implements a thread-safe counter/gauge/histogram registry + `render_prometheus()` in ~150 lines of stdlib. Keeps the container dependency-light and the `/metrics` format is standard 0.0.4 text — a real Prometheus scrapes it fine. Revisit if we need exemplars / native histograms. |
| [`opentelemetry-python`](https://github.com/open-telemetry/opentelemetry-python) | distributed traces | Apache-2.0 | **Deferred, interface reserved.** `OTEL_ENABLED` setting is a documented no-op; wiring the SDK + an OTLP exporter is an operator opt-in (adds ~8 transitive deps). Correlation-id propagation already gives cross-log request tracing. |
| [`sentry-sdk`](https://github.com/getsentry/sentry-python) | error aggregation | MIT | **Deferred, interface reserved.** `SENTRY_DSN` slot; init is a 4-line adapter to add when a DSN exists. The global exception handler + JSON logs + alert dedup cover the gap meanwhile. |
| [`slowapi`](https://github.com/laurentS/slowapi) / [`limits`](https://github.com/alisaifee/limits) | HTTP rate limiting | MIT | **NOT adopted.** `app/ops/rate_limit.py` is a per-(route-class, client) token bucket; no Redis round-trip on the hot path, deterministic in tests. |
| SSRF filtering (no dominant lib; ideas from `advocate`, GitHub SSRF advisories) | block internal/metadata egress | Apache-2.0 (advocate) | **ALGORITHM_REFERENCE.** `app/ops/ssrf.py` resolves DNS and rejects private/loopback/link-local/reserved ranges + metadata hosts + non-http(s) schemes itself. |
| [`pybreaker`](https://github.com/danielfm/pybreaker) | circuit breaker | BSD-3 | **NOT adopted.** `app/ops/circuit_breaker.py` is a small CLOSED/OPEN/HALF_OPEN state machine with per-provider config from settings. |
| [pgBackRest](https://github.com/pgbackrest/pgbackrest) / [Barman](https://github.com/EnterpriseDB/barman) | PG backup + PITR / WAL archiving | MIT / GPL-3 | **RECOMMENDED for a real deployment, not bundled.** Phase 5 uses `pg_dump -Fc` (daily, verified, restore-rehearsed) for RPO ≤ 24 h. pgBackRest (MIT) is the pick for continuous WAL/PITR when a real PG host exists — documented in `DISASTER_RECOVERY.md`. Barman is GPL-3 (operator-run binary, not linked — acceptable, but pgBackRest's MIT is cleaner). |
| [Caddy](https://github.com/caddyserver/caddy) | TLS termination + reverse proxy, automatic ACME | Apache-2.0 | **OPTIONAL_TOOL.** `docker-compose.prod.yml` `proxy` profile + `deploy/Caddyfile`. Operator may swap for nginx/Traefik/a cloud LB. Not required for the app to run. |
| [Grafana](https://github.com/grafana/grafana) (AGPL-3) / [Loki](https://github.com/grafana/loki) (AGPL-3) | dashboards / log aggregation | AGPL-3.0 | **OPERATOR-RUN ONLY, never a dependency or a code reference.** AGPL is fine for a separately-run observability stack the operator deploys; our code neither imports nor derives from it. `/metrics` + JSON-logs-to-stdout are the integration surface. Prometheus itself is Apache-2.0. |

**Net Phase 5 dependency change: none.** All production/security/backup/monitoring
primitives are first-party stdlib code. External tools (Prometheus, Caddy,
pgBackRest, Grafana/Loki, an OTLP collector, Sentry) are *optional, operator-run,
and integrated over standard interfaces* — none are linked into the image.

## GitHub Best-of-Breed Audit (2026-08-31)

Full inventory + per-agent comparison: `docs/AGENT_SKILL_INVENTORY.md`,
`docs/BEST_SKILL_MATRIX.md`. Summary of dependency-relevant conclusions:

**Adopted in code this pass (no new dependency):**
| Idea | From | Type | Where |
|---|---|---|---|
| Tolerant JSON extraction (strip ``` ```json ``` fences, balanced-brace scan) | `instructor` / `outlines` (MIT) | ALGORITHM_PORT | `app/agents/common.py::parse_json` |
| Research query decomposition (rotating angle queries on the fix pass) | `gpt-researcher` (Apache-2.0), STORM (MIT) | ALGORITHM_PORT | `app/agents/nodes.py::_fix_query` |
| Full-jitter exponential backoff | AWS "Exponential Backoff and Jitter" | ALGORITHM_PORT | `app/providers/retry.py` |

**Recommended next (small, low-risk, still no heavy dep):**
| Candidate | License | Type | Target |
|---|---|---|---|
| `textstat` | MIT | DIRECT_DEPENDENCY | naturalness readability sub-signal (`app/naturalness/slop.py`) |
| `trafilatura` | Apache-2.0 | ADAPTER (`PageReader` provider) | research reads source text, not snippets |
| MTLD / lexical-diversity, semantic-repeat (cosine of adjacent sentences) | algorithm | ALGORITHM_PORT | naturalness tells |
| ASS `\k` karaoke tags from `WordTiming` | `pysubs2` idea (MIT) | ALGORITHM_PORT | `app/media/subtitles.py::write_ass` |
| `tenacity` (already a dependency — currently unused) | Apache-2.0 | REFERENCE_ONLY → adopt | unify `providers/retry.py` + `publishing/retry.py` |
| Mem0-style multi-signal retrieval fusion; memory-supersede vs overwrite | Mem0 (Apache-2.0), Graphiti/Zep (Apache-2.0) | ALGORITHM_PORT / ARCHITECTURE_PATTERN | `app/learning/memory.py` |
| SkillRegistry + SkillRouter metadata/gating layer | LangGraph conditional routing | ARCHITECTURE_PATTERN | new `app/skills/` |

**Recommended for later (real benefit, higher regression surface — own task):**
| Candidate | License | Type | Target | Why deferred |
|---|---|---|---|---|
| `model2vec` (or `fastembed`) real multilingual embeddings | MIT / Apache-2.0 | DIRECT_DEPENDENCY behind an `EmbeddingProvider` adapter | replace the 24-dim hashed vector in `app/analytics/embedding.py` | changes cluster ids + similarity across all Phase 3/4 fixtures — highest-leverage upgrade, needs a re-baseline task |
| `whisperx` + `faster-whisper` | BSD-2 / MIT | ADAPTER (finish `WhisperXAlignmentProvider` stub) | real forced alignment in `app/media/word_timing.py` | needs audio fixtures + optional model download |
| `Kokoro-82M` / `Piper` | Apache-2.0 / MIT | ADAPTER (`TTSProvider`) | first real TTS | model infra + audio fixtures |
| `pybandits` | MIT | DIRECT_DEPENDENCY | Thompson-sampling experiment engine (`app/learning/experiment.py`) | changes experiment outcomes Phase-3 tests assert on |
| `ruptures` (+ statsmodels STL, algorithm) | BSD-2 / BSD-3 | DIRECT_DEPENDENCY behind the pure signal functions | change-point-based trend velocity/acceleration (`app/autopilot/signals.py`); calibrate `scoring.py::_WEIGHTS` from stored predicted-vs-actual | signal-coefficient change → autopilot fixture re-baseline |
| `PyOD` / MAD | BSD-2 / algorithm | ALGORITHM_PORT | better outlier test in `app/analytics/performance.py` | affects false-learning guard behaviour |
| `PySceneDetect` / `auto-editor` algorithm | BSD-3 / Unlicense | DIRECT_DEPENDENCY / ALGORITHM_PORT | real-footage cut editing | no real `VideoProvider` yet (already in this file) |
| LangGraph 0.2.60 → 0.6.x + `langgraph-supervisor` | MIT | dependency bump + ARCHITECTURE_PATTERN | `interrupt()` HITL, node caching, durability modes, SkillRouter routing | version bump touches every graph test |
| OpenCV spectral-residual saliency | numpy algorithm | ALGORITHM_PORT | text-safe thumbnail placement (`app/media/thumbnail.py`) | low value while backgrounds are mock gradients |

**Rejected (see `BEST_SKILL_MATRIX.md` for the full list):** CrewAI / AutoGen /
MetaGPT / PydanticAI-graph / DBOS / Temporal / Restate (second runtime — spec
§10/§24); SearXNG / Firecrawl-core / Postiz (AGPL — never a linked dep); Mixpost
(paid); Coqui XTTS (non-commercial weights); edge-tts as prod default (MS ToS);
GPTZero / detector-evasion repos (spec §15); Remotion as the render engine
(employee-gated licence — stays OPTIONAL_TOOL).

## Video Studio Upgrade — component licence register (2026-08-31)

Full comparison: `docs/VIDEO_BEST_SKILL_MATRIX.md`. **Code licence and model/weight
licence checked separately.** No component below is a hard Production dependency;
the ones marked CODE_READY are optional adapters with deterministic fallbacks.

| Repo / component | Code licence | Model / weight licence | Commercial allowed | Attribution | Usage decision | Reason |
|---|---|---|---|---|---|---|
| FFmpeg `zoompan` / `ebur128` / `signalstats` / `freezedetect` / `sidechaincompress` | (bundled build) | n/a | ✅ (already shipped) | — | **IMPLEMENTED** — cinematic motion builders + real QA probes | no new dependency; uses the ffmpeg we already ship |
| Netflix/vmaf (`libvmaf`) | BSD+Patent (was Apache-2.0, changed 2026) | n/a | ✅ | NOTICE | **CODE_READY** `ffmpeg_probe.vmaf()` | ref-vs-encoded quality; degrades to "unavailable" if not compiled in |
| Breakthrough/PySceneDetect | BSD-3 | n/a | ✅ | NOTICE | **OPTIONAL_DEPENDENCY** (later) | shot-boundary-aware cuts once real footage exists |
| WyattBlue/auto-editor | Unlicense → MIT (recent) | n/a | ✅ | — | **ALGORITHM_PORT** (later) | silence cut-list + keep-margins into the Editor Engine |
| SYSTRAN/faster-whisper | MIT | Whisper CT2 weights MIT | ✅ | NOTICE | **CODE_READY** Transcription Provider | fast CPU transcription |
| m-bain/whisperX | BSD-2 | wav2vec2 align models (mostly MIT/Apache) | ✅ | NOTICE | **ADAPTER** (finish the existing stub) | real forced alignment; fallback = estimator |
| NVIDIA NeMo / SpeechBrain (diarization) | Apache-2.0 | Apache-2.0, ungated | ✅ | NOTICE | **CODE_READY** diarization backend | preferred over gated pyannote |
| pyannote.audio | MIT | HF-gated, free-commercial after accepting terms | ⚠️ gated | NOTICE | **REFERENCE_ONLY** | gating is friction for automation |
| facebookresearch/sam2 | Apache-2.0 | **Apache-2.0 weights** | ✅ | NOTICE | **CODE_READY** `adapters/models.segment_subject` | subject masking / smart reframe; GPU; fallback = OpenCV saliency |
| facebookresearch/co-tracker | **CC-BY-NC-4.0** | CC-BY-NC-4.0 | ❌ | — | **REFERENCE_ONLY / DO_NOT_USE** | non-commercial; substitute = OpenCV trackers / SAM 2 |
| opencv/opencv | Apache-2.0 (≥4.5) | n/a | ✅ | NOTICE | **CODE_READY** (`adapters/reframe.py` advanced path) | saliency + trackers + optical flow — licence-safe backbone |
| DepthAnything/Depth-Anything-V2 | Apache-2.0 (code) | **S/B/L = Apache-2.0** ; **Giant = CC-BY-NC-4.0** | ✅ S/B/L · ❌ Giant | NOTICE | **CODE_READY (S/B/L only)** `adapters/models.depth_map` | real parallax; `model_size="giant"` is hard-blocked in code; fallback = `DEPTH_PARALLAX_SIM` |
| xinntao/Real-ESRGAN | BSD-3 (code) | some pretrained weights carry dataset terms | ✅ code / ⚠️ weights | NOTICE | **CODE_READY** `adapters/models.upscale` | quality-gated; adapter carries the weight caveat; gated by `quality.improved()` |
| hzwer/ECCV2022-RIFE | MIT (code) | some model weights **non-commercial** | ✅ code / ⚠️ weights | NOTICE | **CODE_READY** `adapters/models.interpolate` | verify weight licence before commercial use |
| remotion-dev/remotion (+ skills) | source-available; free ≤3 employees / non-profit / eval, else company licence | n/a | ⚠️ size-gated | per licence | **DESIGN_ONLY** | study Agent Skills as patterns; not a hard render dep; keep FFmpeg+Pillow |
| Spotify/pedalboard | **GPL-3** | n/a | ❌ (closed service) | — | **DO_NOT_USE** | GPL-3 would infect the service; use FFmpeg audio filters |
| librosa | ISC | n/a | ✅ | NOTICE | **REFERENCE_ONLY** | beat/onset; in-house RMS onset detector used for now |
| madmom | BSD (parts academic-noted) | mixed | ⚠️ | — | **REFERENCE_ONLY** | licence nuance on parts → not a dep |
| OpenCLIP | MIT | model-dependent (LAION weights mostly OK) | ✅ | NOTICE | **REFERENCE_ONLY / later** | transcript→clip visual match when a real stock library exists |

**Net Video Studio Upgrade dependency change: none.** All `app/video/` modules
(22 after the continuation pass) are deterministic stdlib + the existing
`app.analytics.embedding` + Pillow + the bundled ffmpeg. Heavy items are optional
adapters that raise rather than fake.

**Continuation pass (2026-08-31 part 2) — install policy (`DECISIONS.md` D67):**
capability-gap priority is (1) improve code → (2) architecture pattern → (3)
implement the algorithm → (4) **project-scoped** dependency (`requirements.txt` /
`package.json`) → (5) optional adapter → (6) global tool → (7) user-scope Claude
plugin. 6 and 7 are not used without an approved reason. `uv tool install` /
global npm installs are **not** the default mechanism. Externally-suggested
`DietrichGebert/ponytail`, `@ponytail`, `graphify`, `headroom-ai[proxy,mcp]` are
**not installed** — not required by this project. Continuation pass added
**0 dependencies** (project- or global-scoped): new agent modules
(`app/agents/{research,factcheck,hooks}.py`) and video modules
(`cuts, captions, creative_qa, rerender, technical_qa`) are pure stdlib +
`app.analytics.embedding`.

## Phase 6 — Multi-Brand / Auth / Portfolio / Monetization (2026-09-01)

**Net dependency change: none.** Auth uses stdlib only:
`hashlib.pbkdf2_hmac` for passwords, `hmac`/`hashlib.sha256` (keyed by
`SECRET_KEY`) for API keys, `secrets` for key generation. No `passlib`,
`python-jose`, `authlib`, `fastapi-users`, or an external auth SaaS — a provider-
agnostic local layer with an `IdentityProvider` seam for a future OIDC/SAML
adapter (`docs/SECURITY_MODEL.md`). RBAC, tenant scope, budget reservation,
Channel/Portfolio managers, routing, and Monetization guards are plain SQLAlchemy
+ rules + the existing `app.analytics.embedding`. Install policy D67 upheld:
`DietrichGebert/ponytail`, `@ponytail`, `graphify`, `headroom-ai[proxy,mcp]` are
**not installed** — not required by this project.

## Phase 7 — Content Governance / Rights / Policy / Originality / AI Disclosure (2026-09-01)

**Net dependency change: none.** The whole governance layer (`app/governance/`,
14 tables, 2 gates, 13 API routes) is deterministic: SQLAlchemy + Python stdlib
(`hashlib`, `re`, `statistics`) + the existing `app.analytics.embedding` +
**Pillow** (already a dependency — perceptual hashing is aHash 8×8 + dHash 9×8,
no `imagehash`/`videohash`/PDQ). No LLM is used for a governance verdict.

Evaluated and **NOT adopted** (spec §155–§156, install policy D67):

| candidate | purpose | why not |
|---|---|---|
| `c2pa-python` / Adobe CAI / `truepic` | C2PA / Content Credentials signing | needs a signing identity + trust list + native OpenSSL bindings; few target platforms verify CR for short-form; internal `RightsManifest`+`AssetLineage` cover provenance. Faking a Content Credential is refused. Tracked OPTIONAL. |
| `imagehash` / `videohash` / Facebook PDQ / `pdqhash` | stronger perceptual / video fingerprint | aHash+dHash via Pillow is sufficient for the deterministic tier; a heavy fingerprint is an OPTIONAL adapter slot, not a dependency |
| `python-magic` beyond the existing Phase 5 `ops.upload_security` | screenshot / file sniffing | Phase 5 `sniff_mime` already covers it |
| `langdetect` / `presidio` | PII / language detection in screenshots & scripts | regex PII (`email`/`phone_kr`/`card`/`rrn_kr`) is the deterministic floor; a CV/NER PII detector is an OPTIONAL adapter that routes to review when absent, never a faked pass |
| a rules engine (`durable_rules`, `business-rules`) | policy evaluation | plain Python dict fixtures + `rules_for()` are clearer and versioned |

Externally-suggested `DietrichGebert/ponytail`, `@ponytail`, `graphify`,
`headroom-ai[proxy,mcp]` remain **not installed** — not required by this project.

## Cross-Phase Intelligence Upgrade — URL Learning / Dataset / Prompt Distillation / Platform Selection (2026-09-01)

**Net dependency change: none.** `backend/app/intel/` (URL learning engine,
reference dataset, prompt distillation, agent skill learning, SNS platform
selection; 13 tables, ~25 API routes, 4 frontend pages) is pure stdlib +
existing deps: `html.parser` / `re` / `hashlib` / `statistics` for extraction and
scoring, the existing `app.analytics.embedding` + `app.governance.originality` for
similarity/dedup, and the Phase 5 `app.ops.ssrf` guard. No LLM is required for any
deterministic path.

Evaluated and **NOT adopted** (install policy D67):

| candidate | purpose | why not |
|---|---|---|
| `playwright` / `pyppeteer` / `selenium` | JS-rendered page fetch | real project-scoped dependency **pending approval**; `BrowserFetchAdapter` is a wired seam, off by default (`browser_fetch_enabled`), stub raises rather than faking a render |
| `trafilatura` / `readability-lxml` / `newspaper3k` | HTML main-content extraction | the stdlib `html.parser` cleaner covers nav/footer/ads/script/style stripping + metadata for the deterministic tier |
| `pypdf` / `pdfmin.six` | PDF text | PDFs are handled as `LIMITED` (no parser dependency); a parser is a future project-scoped add |
| `sentence-transformers` / `model2vec` | real embeddings for similarity | same call as D61 — deferred; cheap hash + simhash is the current tier |
| `yt-dlp` / YouTube Data API client | video reference ingest | no scraping; video analysis works from a **caller-supplied** structured profile only |
| `feedparser` | watchlist RSS | watchlist is opt-in and DESIGN_ONLY (no auto-ingest scheduler yet) |

Externally-suggested `DietrichGebert/ponytail`, `@ponytail`, `graphify`,
`headroom-ai[proxy,mcp]` remain **not installed**.

## Rules
1. Any repo whose license is unclear at integration time ⇒ mark `REFERENCE_ONLY`, reimplement from public docs.
2. AGPL/GPL or business-impacting terms ⇒ separate review before use (none of the above are AGPL; edge-tts is LGPL — dynamic-link only, or drop it).
3. `REVIEW REQUIRED` rows must be signed off in this file before their code/weights ship in a paid product.
4. Every `DIRECT_DEPENDENCY` with `attribution_required: true` goes into a `NOTICE` file when that phase lands.
5. Token rule: read only README / LICENSE / the specific feature file — never clone-and-scan a whole repo.

## Phase 10 research — Dashboard design (2026-09-01)

Full audit + scorecard: `docs/DASHBOARD_REFERENCE_AUDIT.md`. Summary:

| Repo | License | Usage | Files/patterns used | Modifications | Reason |
|---|---|---|---|---|---|
| Kiranism/next-shadcn-dashboard-starter | MIT | PATTERN_REFERENCE | URL-synced list state, server pagination default, desktop-table/mobile-card split | reimplemented in our stack; **no file copied** | best structural match; adding shadcn+tanstack deps rejected as bloat |
| satnaing/shadcn-admin | MIT | PATTERN_REFERENCE | responsive nav model, command-palette affordance, empty-state tone, density | reimplemented (`components/AppShell.tsx`) | best nav/UX polish; Vite stack, so pattern only |
| reoring/next-shadcn-admin | MIT | PATTERN_REFERENCE | Next App Router shell placement, `md:` breakpoints | reimplemented | Next port of satnaing |
| TailAdmin/free-nextjs-admin-dashboard | MIT (free tier) | PATTERN_REFERENCE | KPI card grid rhythm, agenda-on-mobile calendar, status cards | reimplemented | pro-tier widgets NOT used |
| tremorlabs/template-dashboard-oss | Apache-2.0 | PATTERN_REFERENCE | analytics KPI hierarchy (headline→delta→sparkline→detail) | reimplemented | **Tremor npm package NOT added** |
| tremorlabs/template-dashboard (commercial) | non-permissive | REFERENCE_ONLY (visual) | — | none | code copy forbidden; visual study only |
| shadcn-ui/ui dashboard example | MIT | PATTERN_REFERENCE | card/table spacing | reimplemented | shadcn CLI/runtime not added |
| horizon-ui/horizon-tailwind-react-nextjs | MIT (free) | REJECTED | — | none | heavy dep tree, strong visual identity |

**0 files copied. 0 new npm dependencies.** The dashboard is AI Content Factory's
own design system (`tailwind.config.ts` tokens + `globals.css` component layer).
No external install script / README command / postinstall was executed.
