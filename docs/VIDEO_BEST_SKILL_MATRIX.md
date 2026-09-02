# VIDEO BEST-OF-BREED SKILL MATRIX

Video Studio Upgrade — OSS survey per video sub-discipline, with the code-vs-model
licence split and a decision. Reviewed 2026-08-31 (web survey + prior knowledge).
Companion: `docs/VIDEO_ARCHITECTURE.md`, `docs/OPEN_SOURCE_COMPONENTS.md`.

Decision vocabulary: `DIRECT_DEPENDENCY` · `OPTIONAL_DEPENDENCY` (CODE_READY
adapter) · `ADAPTER` · `ALGORITHM_PORT` · `ARCHITECTURE_PATTERN` ·
`PROMPT_PATTERN` · `REFERENCE_ONLY` · `DO_NOT_USE`.

Rule applied throughout: **a non-commercial model or weight is never a Production
dependency** — REFERENCE_ONLY, with a commercial-safe alternative named.

---

## Scene / Shot detection

| Repo | Code licence | Model/weight licence | Commercial | Decision |
|---|---|---|---|---|
| **Breakthrough/PySceneDetect** | BSD-3 | n/a (classical) | ✅ | **OPTIONAL_DEPENDENCY** — shot-boundary detection for real footage; ensure our narration cuts don't fall across a detected shot (B13). Not needed until a real `VideoProvider`/user footage exists. |
| **TransNetV2** | MIT | MIT | ✅ | REFERENCE_ONLY — better than PySceneDetect on hard cuts but a torch model; revisit if PySceneDetect proves weak. |
| **WyattBlue/auto-editor** | Unlicense→MIT (recent) | n/a | ✅ | **ALGORITHM_PORT** — silence/dead-air cut list with keep-margins (80–350 ms), motion-aware trimming. Port the margin + loudness-gate ideas into the Editor Engine; do not add as a dep. |
| OpenCV optical flow (`calcOpticalFlowFarneback`) | Apache-2.0 (≥4.5) | n/a | ✅ | **OPTIONAL_DEPENDENCY** — cut-on-action point finding (B12); fallback = beat/sentence cut. |

## Transcription / Alignment / Diarization

| Repo | Code | Model | Commercial | Decision |
|---|---|---|---|---|
| **SYSTRAN/faster-whisper** | MIT | CT2 Whisper weights (MIT) | ✅ | **OPTIONAL_DEPENDENCY** — Transcription Provider (fast, CPU-ok). |
| **m-bain/whisperX** | BSD-2 | wav2vec2 align models (MIT/Apache mostly) | ✅ | **ADAPTER** — finish `WhisperXAlignmentProvider` (currently a stub that raises). Real forced alignment; fallback = existing `EstimatorAlignmentProvider`. |
| stable-ts | MIT | Whisper weights | ✅ | REFERENCE_ONLY — single-package word timestamps; whisperX preferred for the diarization tie-in. |
| **pyannote.audio** | MIT (code) | HF-gated, **free for commercial after accepting terms** | ⚠️ gated | REFERENCE_ONLY — gating is friction for an automated pipeline. |
| **NVIDIA NeMo** / **SpeechBrain** diarization | Apache-2.0 | Apache-2.0, **ungated** | ✅ | **OPTIONAL_DEPENDENCY** — preferred diarization backend (B35). Only runs for multi-speaker content. |
| ElevenLabs Scribe v2 | proprietary API | — | 💲 paid | REFERENCE_ONLY — not OSS. |

## Subject segmentation / Tracking / Reframe

| Repo | Code | Model | Commercial | Decision |
|---|---|---|---|---|
| **facebookresearch/sam2** | Apache-2.0 | **Apache-2.0 weights** | ✅ | **OPTIONAL_DEPENDENCY (CODE_READY)** — subject masking / smart reframe / tracked highlight / background treatment (B20, B21). GPU. Fallback ladder: OpenCV saliency crop → rule-of-thirds safe crop. |
| **facebookresearch/co-tracker** | **CC-BY-NC-4.0** (code + weights) | CC-BY-NC-4.0 | ❌ non-commercial | **REFERENCE_ONLY** — study the point-tracking approach; **do not integrate**. Commercial-safe substitute: OpenCV `TrackerCSRT`/`TrackerKCF` (Apache-2.0) or SAM 2 mask propagation. |
| **opencv/opencv** | Apache-2.0 (≥4.5) | n/a | ✅ | **OPTIONAL_DEPENDENCY** — saliency (`StaticSaliencySpectralResidual`), trackers, optical flow. This is the license-safe backbone for reframe/tracking. Implemented as the `smart_reframe` advanced path + `dynamic_reframe_track` smoothing (dead-zone + max-pan). |
| Smart-crop / auto-reframe services | proprietary | — | 💲 | REFERENCE_ONLY. Our `safe_reframe_box` already avoids naive centre-crop (rule-of-thirds, subject-biased). |

## Depth / Image motion

| Repo | Code | Model | Commercial | Decision |
|---|---|---|---|---|
| **DepthAnything/Depth-Anything-V2** | Apache-2.0 (code) | **S/B/L = Apache-2.0** ; **Giant = CC-BY-NC-4.0** | ✅ S/B/L · ❌ Giant | **OPTIONAL_DEPENDENCY (CODE_READY)** for S/B/L only — real fore/mid/background parallax. `adapters/models.depth_map` **hard-blocks `model_size="giant"`**. Fallback = `DEPTH_PARALLAX_SIM` (implemented, no model). |
| MiDaS | MIT | MIT | ✅ | REFERENCE_ONLY — older; Depth-Anything-V2 S/B/L is better and equally permissive. |
| FFmpeg `zoompan` (built-in) | LGPL/GPL (our build) | n/a | ✅ (we already ship it) | **IMPLEMENTED** — `app/video/motion.py` builds 8 cinematic `zoompan`/crop-drift expressions (`KEN_BURNS, DEPTH_PARALLAX_SIM, DOLLY_IN_SIM, DOLLY_OUT_SIM, SUBJECT_PUSH, BACKGROUND_DRIFT, SLOW_ORBIT_SIM, FOCUS_PULL_SIM`). Gentle rates; `*_SIM` labels are honest. |

## Motion graphics / Kinetic typography

| Repo | Code / licence | Commercial | Decision |
|---|---|---|---|
| **remotion-dev/remotion** + `remotion-dev/skills` | source-available; **free ≤3 employees / non-profit / eval**, else company licence ($100/mo min, or $0.01/render for automation) | ⚠️ size-gated | **DESIGN_ONLY** — study the official Agent Skills (composition/timing/animation/typography/audio/captions/layout) as `ARCHITECTURE_PATTERN`/`PROMPT_PATTERN`; do **not** make Remotion a hard render dependency. Keep FFmpeg + Pillow graphics; revisit only if a paid Company Licence is acquired. |
| `pysubs2` | MIT | ✅ | REFERENCE_ONLY — ASS handling. Our `write_ass` / new `write_ass_kinetic` (`\k` karaoke) are hand-rolled and sufficient. |
| MoneyPrinterTurbo | MIT | ✅ | REFERENCE_ONLY (already in registry) — kinetic-caption + BGM structuring ideas. |

## Audio: beat / loudness / processing

| Repo | Code | Commercial | Decision |
|---|---|---|---|
| **librosa** | ISC | ✅ | REFERENCE_ONLY / possible small DIRECT_DEPENDENCY — beat/onset/tempo. For now a lightweight deterministic RMS-energy onset detector (no dep) covers "cut on important beats only" (B42). |
| **madmom** | BSD-ish (some parts academic-noted) | ⚠️ check | REFERENCE_ONLY — most accurate offline beat tracking; licence nuance → avoid as a dep. |
| BeatNet | MIT | ✅ | REFERENCE_ONLY — real-time; we don't need real-time. |
| **Spotify/pedalboard** | **GPL-3** | ❌ for a closed commercial service | **DO_NOT_USE** as a dependency — GPL-3 would infect the service. Use FFmpeg filters (`acompressor`, `sidechaincompress`, `loudnorm`, `alimiter`) which we already ship. |
| FFmpeg `ebur128` / `loudnorm` / `sidechaincompress` (built-in) | our build | ✅ | **IMPLEMENTED** — ducking envelope in `audio_plan.py`; real integrated-LUFS + true-peak measured by `ffmpeg_probe.check_loudness` (ebur128). Loudness targets are operator profiles, not claimed platform specs. |
| **Netflix/vmaf** (`libvmaf`) | **BSD+Patent** (changed from Apache-2.0 in 2026) | ✅ | **OPTIONAL_DEPENDENCY (CODE_READY)** — `ffmpeg_probe.vmaf(ref, distorted)`; ref-vs-encoded quality check; degrades to "not available" if the ffmpeg build lacks libvmaf. |

## Enhancement / Restoration

| Repo | Code | Model weights | Commercial | Decision |
|---|---|---|---|---|
| **xinntao/Real-ESRGAN** | BSD-3 | some pretrained weights carry dataset terms | ✅ code / ⚠️ weights | **OPTIONAL_DEPENDENCY (CODE_READY)** — quality-gated upscale; adapter carries the weight-verification caveat; only applied if `quality.improved(before, after)` confirms a gain (B67). |
| **hzwer/ECCV2022-RIFE** | MIT (code) | some model weights **non-commercial** | ✅ code / ⚠️ weights | **OPTIONAL_DEPENDENCY (CODE_READY)** — frame interpolation for low-FPS generated clips; verify weight licence before commercial use; QA before/after. |
| Video restoration (BasicVSR++, etc.) | mostly Apache/MIT code, mixed weights | ⚠️ | REFERENCE_ONLY — revisit only when real low-quality footage is in the pipeline. |

## B-roll / semantic retrieval

| Repo | Code | Commercial | Decision |
|---|---|---|---|
| **OpenCLIP** | MIT | ✅ | REFERENCE_ONLY now / OPTIONAL_DEPENDENCY later — transcript-segment → clip visual-similarity match (the real upgrade for `mock_stock`'s keyword search). Our `broll.py` uses the existing hashed `embed()` for semantic scoring today; swap to CLIP frame embeddings when a real stock library exists. |
| Grounding DINO / TransNetV2 | Apache/MIT | ✅ | REFERENCE_ONLY — object/shot tagging to enrich a stock index. |
| opensource-clipping / OpenShorts | MIT | ✅ | REFERENCE_ONLY — kinetic captions, face-tracking, contextual B-roll patterns. |

---

## Applied in code this session (deterministic, no new dependency)

| Area | Module | Type |
|---|---|---|
| Video Director + Story/Emotion/Retention/Boredom/Shot-Grammar/Pacing/B-roll/Voice-V2/Audio/Colour/Timeline/Quality-V2/Router/Registry/Editor-Memory | `app/video/*` | ALGORITHM_PORT / ARCHITECTURE_PATTERN (patterns from gpt-researcher-style planners, auto-editor margins, ShortGPT beats, editorial shot grammar) |
| 8 cinematic FFmpeg image-motion builders | `app/video/motion.py` (+ `app/media/image_motion.py` delegation) | ALGORITHM_PORT |
| ASS `\k` kinetic captions | `app/media/subtitles.py::write_ass_kinetic` | ALGORITHM_PORT (pysubs2 idea) |
| Real ffmpeg QA probes (ebur128 / signalstats / freezedetect / A-V drift / libvmaf) | `app/video/ffmpeg_probe.py` | uses the bundled ffmpeg — no new dep |
| Creative plan + Video QA v2 wired into the media pipeline (additive) | `app/agents/media_nodes.py` | — |

## CODE_READY optional adapters (interface + fallback; never faked)

`app/video/adapters/` — SAM 2 segmentation, Depth-Anything-V2 (S/B/L) depth,
OpenCV tracking + smart reframe, NeMo/SpeechBrain diarization, WhisperX alignment,
Real-ESRGAN upscale, RIFE interpolation. Each raises `OptionalSkillUnavailable`
unless its dep is installed (and, for Depth-Anything Giant / non-commercial RIFE
weights, it stays blocked). The router points to a deterministic fallback.

## Rejected for Production

| Repo | Reason | Commercial-safe substitute |
|---|---|---|
| facebookresearch/co-tracker | CC-BY-NC-4.0 (code + weights) | OpenCV trackers (Apache-2.0) / SAM 2 mask propagation |
| Depth-Anything-V2 **Giant** | CC-BY-NC-4.0 weights | Depth-Anything-V2 S/B/L (Apache-2.0) |
| Spotify/pedalboard | GPL-3 (infects a closed service) | FFmpeg audio filters (already shipped) |
| Remotion as a hard render dep | company licence ≥4 employees | FFmpeg + Pillow graphics; Remotion optional if a licence is bought |
| Coqui XTTS (from the agent audit) | non-commercial weights | Kokoro (Apache-2.0) / Piper (MIT) |
| madmom as a dep | licence nuance on parts | librosa (ISC) or the in-house RMS onset detector |
