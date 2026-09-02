# VIDEO ARCHITECTURE — Advanced Video Studio

Video Studio Upgrade (2026-08-31). How the video-production team is structured
after the upgrade, what is an LLM call vs a deterministic Engine, and how skills
are routed per campaign. Code lives in `backend/app/video/`. Wiring points are in
`backend/app/agents/media_nodes.py` and `backend/app/media/`.

**This is not AI-detection evasion.** Every skill here targets editorial quality,
rhythm, meaningful visuals, sound, captions, retention, and creative variety.
Platform AI-disclosure requirements are kept.

Status legend: **IMPLEMENTED** (deterministic code + tests + wired) ·
**CODE_READY** (interface + fallback exist, optional heavy dep/GPU not assumed;
raises `OptionalSkillUnavailable`, never fakes) · **DESIGN_ONLY** (documented, not
built — licence or scope).

---

## 1. Team structure (which are LLM, which are Engines)

```
                         VIDEO DIRECTOR                 [Engine — app/video/director.py]
                                │  builds VideoCreativePlan (no LLM)
        ┌───────────────────────┼────────────────────────┐
   STORY DIRECTOR        RETENTION DIRECTOR         VISUAL DIRECTOR
   [Engine story.py]     [Engine retention.py]      [Engine app/media/visual_director.py + shots.py]
        │                        │                          │
        └──────────┬─────────────┘                          │
             SCENE PLANNER  [LLM — media_nodes.scene_plan]  │
                   │  (existing; unchanged)                 │
             SHOT DIRECTOR  [Engine shots.py] ──────────────┘
                   │
      ┌────────────┼───────────────────────────┐
 B-ROLL DIRECTOR   MOTION DIRECTOR       GRAPHICS DIRECTOR
 [Engine broll.py] [Engine motion.py]    [Engine app/media/chart.py,thumbnail.py; Remotion DESIGN_ONLY]
      │                  │                        │
      └────────────┬─────┴────────────────────────┘
             VOICE DIRECTOR  [Engine voice_plan.py]   (TTS provider unchanged / mock)
                   │
             SOUND DIRECTOR  [Engine audio_plan.py + ffmpeg mix in renderer.py]
                   │
             SUBTITLE DIRECTOR [Engine app/media/subtitles.py (+ write_ass_kinetic)]
                   │
             VIDEO EDITOR   [Engine timeline.py (EditDecision V2) + existing edit_decision LLM]
                   │
             COLOR / FINISH [Engine color.py; grade = separate asset, non-destructive]
                   │
             RETENTION QA   [Engine retention.py + quality.py]
                   │
             CREATIVE DIRECTOR [Engine quality.py — VideoQualityScoreV2]
                   │
             TECHNICAL QA   [Engine app/media/media_qa.py + app/video/ffmpeg_probe.py]
```

**LLM calls in the video path stay at 3** (platform_adapt, scene_plan,
edit_decision — all pre-existing). Every Director added by this upgrade is a pure
deterministic Engine. No new runtime dependency. LangGraph remains the single
runtime; the creative direction runs *inside* the existing `scene_plan` node
(additive, no new graph node → no checkpoint-topology change).

---

## 2. Data flow

`scene_plan_node` (existing LLM scene planner)
 → **`app.video.director.direct_video(...)`** builds a `VideoCreativePlan`
 → each scene dict is enriched with `story_beat, emotion_intent, shot_size,
   shot_purpose, motion_energy, primary_focus, cinematic_motion, kinetic_caption,
   visual_evidence_priority` (extra keys — nothing downstream that ignores them
   is affected)
 → the full plan is stored on `PlatformContent.payload["creative_plan"]` and in
   `MediaState["creative_plan"]`
 → `image_motion.render_scene_clip` renders cinematic motions via
   `app.video.motion.zoompan_expr` when a scene asks for one (legacy motions
   unchanged)
 → `media_qa_node` additionally computes **`video_qa`** (`VideoQualityScoreV2` +
   bad-scene detection) — advisory, never blocks `persist` (that stays
   `media_qa` + `compliance`).

`camera_motion`, scene durations, and `visual_type` chosen by the existing
pipeline are **never overwritten** — the upgrade is strictly additive so the
Phase 1-B regression is unaffected.

---

## 3. The Directors (B1–B109 mapping)

| Spec area | Module | Status | What it does |
|---|---|---|---|
| B1 Video Director | `director.py` | IMPLEMENTED | orchestrates all Engines into `VideoCreativePlan` (story_arc, visual/editing/shot language, voice/sound/caption/colour direction, retention strategy, budget distribution, high-impact scenes, skill routing, warnings) |
| B2 Story Director / B3 Emotional Arc | `story.py` | IMPLEMENTED | beat-cue mapping → `HOOK…CTA` per scene + smoothed emotion curve (`curiosity→tension→…→relief`); guarantees a `PAYOFF` before `CTA`; never forces all 13 beats |
| B4 Retention Director / B5 Checkpoints / B6 Boredom | `retention.py` | IMPLEMENTED | first-second strength, early-payoff test, open-loop count, per-checkpoint "reason to stay" + risk (short: 0/1/3/5/10s/50/75%/CTA; long: intro/30s/1m/50/75%/CTA), `boredom_scan` → `BOREDOM_RISK_SCORE` + low-variation spans + pattern-interrupt scenes. **No fake retention curve** — design signals only until Phase-3 data exists (B94) |
| B7 Shot Grammar / B8 Sequence Rule / B27 Camera Continuity / B28 Motion Energy | `shots.py` | IMPLEMENTED | shot size + purpose per scene from beat/content; breaks `SHOT_SCALE_REPETITION` (≥3 identical) by nudging one toward mid-scale; `CAMERA_MOTION_REPETITION` + `MECHANICAL_ALTERNATION` (A/B/A/B) detection; motion energy LOW/MED/HIGH from beat+emotion; picks a cinematic motion per `(energy, purpose)` |
| B9 Continuity | `shots.py` + `timeline.py::timeline_issues` | IMPLEMENTED (partial) | shot-scale + camera-direction jump flags; screen-direction/lighting continuity is DESIGN_ONLY (needs real footage) |
| B10 Cut Logic / B12 Cut Engine V2 | `cuts.py` | IMPLEMENTED | `score_cuts()` scores every candidate: scene boundary (HARD) + one SOFT mid-scene point from emphasis/reaction/phrase-boundary/audio-onset; story-beat-change / visual-change / information-change / audio-onset reasons; min-gap enforcement; `cut_rhythm_report()` flags `MECHANICAL` fixed-interval cutting |
| B11 J/L-cut / Cut-on-action | `timeline.py`, `adapters/` | IMPLEMENTED (structure) / CODE_READY (motion-peak) | J/L-cut = VOICE clip start/end offset from VIDEO_MAIN (fields present); cut-on-action needs optical flow (OpenCV adapter, CODE_READY) |
| B11 ContinuityScore | `quality.py::continuity_score`, `shots.py` | IMPLEMENTED | 1.0 − 0.12·(shot/camera continuity issues) |
| B13 PySceneDetect / B14 auto-editor | see `VIDEO_BEST_SKILL_MATRIX.md` | DESIGN_ONLY | ALGORITHM_PORT planned when a real `VideoProvider`/`StockProvider` exists; margins + shot-boundary-aware cut logic |
| B15–B19 B-roll Director | `broll.py` | IMPLEMENTED | 9-axis score (semantic/narrative/emotional/visual/motion/shot-compat/novelty/license/context); kind classification `DIRECT/CONTEXTUAL/METAPHORICAL/ATMOSPHERIC/PROOF/PROCESS/DETAIL` incl. a small metaphor map; story-sequence score (progression not random cuts); `visual_evidence_priority` (prefer chart/screenshot/real doc when a claim/number is made); "pretty but meaningless" penalty |
| B20–B24 Segmentation / SAM 2 / Tracking / Reframe | `adapters/reframe.py`, `adapters/models.py` | CODE_READY | `safe_reframe_box` (rule-of-thirds, subject-biased — never naive centre crop) always works; `smart_reframe_box` uses OpenCV saliency when installed; SAM 2 (Apache-2.0) + OpenCV trackers behind `OptionalSkillUnavailable`; `dynamic_reframe_track` smoothing (dead-zone + max-pan) |
| B25 Depth Motion / B26 Cinematic Image Motion | `motion.py`, `adapters/models.py::depth_map` | IMPLEMENTED (sim) / CODE_READY (real depth) | 8 cinematic FFmpeg builders: `KEN_BURNS, DEPTH_PARALLAX_SIM, DOLLY_IN_SIM, DOLLY_OUT_SIM, SUBJECT_PUSH, BACKGROUND_DRIFT, SLOW_ORBIT_SIM, FOCUS_PULL_SIM` — honestly `*_SIM` (no depth model); gentle rates, no over-done fake camera. Real depth = Depth-Anything-V2 **S/B/L (Apache-2.0)** adapter; **Giant is CC-BY-NC-4.0 → blocked** |
| B29–B31 Motion Graphics / Remotion / Kinetic Typography | `subtitles.py::write_ass_kinetic`; Remotion DESIGN_ONLY | IMPLEMENTED (kinetic captions) / DESIGN_ONLY (Remotion) | ASS `\k` karaoke reveal from real word timings (falls back to even split); kinetic caption assigned only on `HOOK/PROOF/SURPRISE/PAYOFF` scenes (not every word). Remotion is source-available with a company licence ≥4 employees → not a hard dep; keep Pillow/FFmpeg graphics |
| B32 Caption Composition / B34 Caption Collision | `captions.py` | IMPLEMENTED | `resolve_placement(text, avoid_zones)` picks a vertical band (lower-third → lower-mid → upper-third → center) that doesn't overlap face/speaker/chart/ui/platform-safe-zone; `emphasis_words()` = numbers first then one emotion word (≤2, not every word); `caption_load_ok()` chars-per-second reading-speed check |
| B35 Cognitive Load reduce actions | `pacing.py::reduce_actions` | IMPLEMENTED | per overloaded scene → `reduce_caption` / `simplify_visual` / `reduce_effect` / `extend_scene` |
| B33 WhisperX / B34 faster-whisper / B35 Diarization | `adapters/models.py`; `app/media/word_timing.py` (existing stub) | CODE_READY | transcription (faster-whisper, MIT) and alignment (WhisperX, BSD-2) split into two providers; diarization prefers **NeMo / SpeechBrain (Apache-2.0, ungated)** over gated pyannote; only runs for multi-speaker content |
| B36 Voice Director V2 / B37 Prosody Consistency | `voice_plan.py` | IMPLEMENTED | per-phrase `speed/energy/emotion/emphasis/pause_before/pause_after/pitch/volume_intent/delivery_style` from punctuation + emphasis cues + beat; clamped into a brand band; `VoiceConsistencyScore` penalises "different narrator every sentence" |
| B38–B45 Audio / Sound Director | `audio_plan.py`; mix in `app/media/renderer.py` (existing sidechaincompress) | IMPLEMENTED (plan) | music structure (intro/build/drop/break/outro mapped onto the timeline), **ducking envelope** with slow attack/release (≥0.25s/≥0.45s → no pumping), `SFX_DENSITY_SCORE` + HIGH flag, sound-energy curve follows the story arc, loudness **target profiles** (`SOCIAL_STANDARD -14 LUFS` etc. — explicitly operator-tunable, NOT claimed as an official platform spec). Real integrated-LUFS / true-peak measured post-render by `ffmpeg_probe.check_loudness` (ebur128). Audio-processing libs with GPL (e.g. Pedalboard is GPL-3) → REFERENCE_ONLY |
| B29 Natural Pauses | `voice_plan.py::classify_pause` | IMPLEMENTED | every phrase pause classified `BREATH / EMPHASIS / DRAMATIC / UNNECESSARY / NONE` — breath + dramatic pauses are kept, not stripped |
| B32 Audio QA | `technical_qa.py` pass 3 + `ffmpeg_probe.check_loudness` | IMPLEMENTED | integrated LUFS, true-peak, offset-from-target, audio-stream presence; `OFF_TARGET` on near-silent mock audio (correct — the content is quiet) |
| B46–B48 Color Director | `color.py` | IMPLEMENTED | Pillow brightness/contrast/saturation/temperature stats per source; median-match plan (`max_adjust 0.12` — gentle, never a hard grade); applied as a **new asset** (non-destructive); `BrandColorLanguage` from `brands/<brand>/color_language.json`. Real per-frame signalstats = `ffmpeg_probe.color_stats` |
| B48 Technical QA V2 (multipass) | `technical_qa.py` | IMPLEMENTED | `run()` = 7 passes on the real file (file integrity / video technical / audio loudness / audio stream / freeze frames / A-V sync / colour consistency / VMAF); each pass OK/WARN/FAIL/UNKNOWN/SKIPPED; UNKNOWN = filter absent in this ffmpeg build → not a failure. Wired into `media_qa_node.video_qa.technical_qa` |
| B49–B55 Visual Quality / VMAF / Freeze / Black / A-V Sync | `quality.py`, `ffmpeg_probe.py`, `technical_qa.py`, `media_qa.py` | IMPLEMENTED (freeze/black/sync/loudness/colour) / CODE_READY (VMAF) | `freezedetect` (long freezes only WARN — short ones on stills/text-cards expected), `blackdetect`, `ebur128`, `signalstats`, start-time A/V drift. VMAF (`libvmaf`, BSD+Patent) CODE_READY — ref-vs-encoded only, degrades to `SKIPPED`/`UNKNOWN` |
| B47 Creative QA V2 | `creative_qa.py` | IMPLEMENTED | 12 deterministic checks: AI-visual overuse, generic stock, repetitive zoom / captions / transitions, generic music, flat voice, weak story arc, over/under-editing, visual mismatch, same-recent-format → OK/WARN/FAIL + score. Wired into `video_qa.creative_qa` |
| B43 Smart Rerender | `rerender.py` | IMPLEMENTED | per-stage input hashes → `RerenderPlan`; a subtitle-only change rebuilds subtitles + composition, **not** scene clips or voice; a one-scene B-roll swap rebuilds that one clip + composition; `is_noop` when nothing changed |
| B49 Video Quality Score (0–100) + B45 Repair plan | `quality.py::score_100`, `plan_repairs` | IMPLEMENTED | 16-dim score exposed 0–100; `plan_repairs(bad_scenes)` → ordered, de-duped worklist (≤4) mapping each flag to a repair strategy; full re-render is never in the list |
| B51 Quality-based Encode | `quality.py` (profiles) + existing renderer | DESIGN_ONLY | `FAST_PREVIEW/SOCIAL_STANDARD/HIGH_QUALITY/ARCHIVE` profile constants defined; renderer still uses one x264 veryfast profile — wiring the CRF/bitrate switch is a follow-up |
| B56–B60 Frame-accurate Timeline / EditDecision V2 / Non-destructive / Edit History | `timeline.py`, `schema.py` | IMPLEMENTED | `VideoTimeline` (fps/timebase), `TimelineClip` with frame-accurate `frame_start/frame_end`, 7 tracks (`VIDEO_MAIN/OVERLAY/GRAPHICS/CAPTION/VOICE/MUSIC/SFX`), transforms live on clips (source never mutated), `EditHistoryEntry` schema; `timeline_issues()` flags overlaps/gaps/zero-length |
| B57 Timebase | `schema.TIMEBASES`, `timeline.snap()` | IMPLEMENTED | 23.976–60; times snap to frame boundaries so fps conversion doesn't drift |
| B61 Scene Confidence / B62 Bad-Scene Detector / B63 Auto-Repair | `quality.py` | IMPLEMENTED | 11 flags (`LOW_RELEVANCE, LOW_QUALITY, VISUAL_REPETITION, BAD_CROP, WRONG_ASPECT, TEXT_ERROR, TIMING_ERROR, BORING, VOICE_ISSUE, AUDIO_ISSUE, SOURCE_RISK`) → `REPAIR_STRATEGY` map (`broll_reselect / smart_reframe / alternate_or_enhance / …`); full re-render is last resort |
| B64–B67 Real-ESRGAN / RIFE / Restoration / No Quality Theatre | `adapters/models.py`, `quality.improved()` | CODE_READY | upscale/interpolate adapters raise `OptionalSkillUnavailable` with the weight-licence caveat; `improved(before, after, min_gain)` gates any enhancement on a measured metric delta |
| B68–B71 Thumbnail Director V2 | existing `app/media/thumbnail.py` + `VIDEO_BEST_SKILL_MATRIX.md` | DESIGN_ONLY (this pass) | multi-candidate + saliency text-placement + safe-text + diversity — spectral-residual saliency (numpy) planned; low value while backgrounds are mock gradients |
| B72–B75 Edit Profiles / Platform Visual Grammar | `director.py::_PROFILE_BY_CT`, `_caption_style_for` | IMPLEMENTED (short/long) / partial | short-form vs long-form pacing bands + caption density; `DOCUMENTARY/NEWS/DATA_DRIVEN/…` style hooks present; per-platform visual-grammar table is a follow-up |
| B76–B82 Visual Refresh / Info Density / Cognitive Load / Focus / Effect Budget / Editing Intent / Pattern Interrupt | `pacing.py` | IMPLEMENTED | visual-refresh rate vs a per-content-kind comfort band (`TOO_FAST/OK/TOO_SLOW`); new-info units/sec; cognitive-load from simultaneous channels → `overload_scenes`; `PRIMARY_FOCUS` per scene; `edit_intent` per scene; `effect_budget` (fewer when load high, more for hook/surprise); pattern-interrupt scenes from the boredom scan (not mechanical) |
| B83 Comedic Timing | `schema` (delivery_style) | DESIGN_ONLY | pause/reaction/cut-delay hooks reserved; only for humour content |
| B84 Sound Design Story | `audio_plan.sound_energy_curve` | IMPLEMENTED | audio energy per scene follows the beat map, flat-curve warning |
| B85 Source Provenance / B86 User Footage / B87 Best Take / B88 Director's Cut / B89 Cost Guard | `provenance` fields on `Asset` (existing `meta`), `VIDEO_BEST_SKILL_MATRIX.md` | partial / DESIGN_ONLY | provenance fields already on `Asset.meta` + `provider_mode`; best-take ranking = B-roll ranker generalised; director's-cut candidates + multi-candidate cost guard are Phase-4-budget-allocator work |
| B90 Preview Render / B91 Render Cache / B92 Smart Re-render | `VIDEO_BEST_SKILL_MATRIX.md` | DESIGN_ONLY / partial | asset cache (`AssetCache`, composition-hash) already exists for stills/clips; low-res preview pass + a full render-dependency graph are follow-ups |
| B93 Video Quality Score V2 | `quality.py::score` | IMPLEMENTED | 16 weighted dimensions (`story, hook, retention_design, visual_relevance, shot_variety, continuity, edit_rhythm, voice, sound_design, subtitle, graphics, color, technical, naturalness, originality, platform_fit`) |
| B94 Retention Prediction | `quality.py` / Phase 3 | DESIGN_ONLY | feature list defined; **no predicted score emitted while Phase-3 retention data is thin** (spec B94) |
| B95 Skill Versioning / B96 Skill Analytics | `registry.py` | IMPLEMENTED (registry) | `VideoSkill(skill_id, version, algorithm, dependencies, fallback, quality/cost/latency impact, enabled, status)`; version tags ready to join `ContentFeature.prompt_versions` for Phase-3 attribution (wiring is a follow-up) |
| B101 Skill Router / B102 Quality Profiles / B103 GPU Skills / B104 Fallback Ladder | `router.py` | IMPLEMENTED | `route(platform, content_type, profile, budget, risk, opportunity, gpu_available, is_short, multi_speaker)` → `{required, optional, disabled, fallbacks, reasons}`; `FAST/STANDARD/PREMIUM/CINEMATIC` min-rank per skill; GPU skills → fallback ladder when no GPU worker; CINEMATIC flagged as needing budget-allocator approval |
| B105 Editor Memory | `memory.py` | IMPLEMENTED | records a style fingerprint (`cinematic_motions/shot_sizes/caption_style/music`) into `LearningMemory(VISUAL, editor_style)`; `recent_style()` surfaces overused-motion patterns → Video Director adds an "avoid" warning |
| B106 Human Edit Presets | `schema` / dashboard | DESIGN_ONLY | creative-control fields (pace, caption density, b-roll density, music energy, graphics amount, ai-video ratio, transitions, cinematic motion, humour, seriousness) reserved for the dashboard + autopilot bounds |
| B107–B108 Video Dashboard / Retention Map UI | `frontend/app/campaigns/[id]/studio/page.tsx`; `GET /api/campaigns/{id}/media` now returns `creative_plan` + `video_qa` | IMPLEMENTED | Video Studio page: story arc, **retention map of design signals** (checkpoints + high-impact scenes on the timeline, labelled "not a predicted curve"), scene-direction table, routed skills, 16-dim quality score bars, Creative QA + Technical QA verdicts, repair plan. `tsc` + `next build` clean. Scene-level Preview/Regenerate/Replace controls remain on the existing `/media` page |

---

## 4. Quality profiles (B102)

| Profile | Intent | Adds over the one below | Approval |
|---|---|---|---|
| **FAST** | trend speed | story + retention + shot grammar + pacing + timeline + quality score + editor memory (all deterministic, no extra render cost) | — |
| **STANDARD** | natural high quality | + B-roll ranking, cinematic motion, voice V2, audio director, kinetic captions | — |
| **PREMIUM** | high-value pieces | + colour director, loudness QA, colour-stats probe, tracking fallback, diarization (if multi-speaker), WhisperX alignment | — |
| **CINEMATIC** | top opportunities only | + VMAF, SAM 2 segmentation, depth parallax, Real-ESRGAN, RIFE, Remotion graphics (all CODE_READY / need a GPU worker) | **budget-allocator approval** |

GPU skills only become `required` on a profile if `gpu_available=True`; otherwise
they are `optional` and routed to a deterministic fallback (`FALLBACK_LADDER`).

---

## 5. What this upgrade deliberately does NOT do

- No new runtime dependency, no second agent runtime, no GPU assumed.
- No `camera_motion` / duration / `visual_type` overwrite in the existing
  pipeline — additive only, so Phase 1-B stays green.
- No fabricated retention numbers, no "quality theatre" (enhancement counts only
  with a measured before/after).
- No AI-detection-evasion feature. AI-disclosure is kept.
- Non-commercial models/weights (Depth-Anything Giant, CoTracker, some RIFE
  weights, Coqui XTTS) are **blocked from Production** — REFERENCE_ONLY, with a
  commercial-safe alternative named in `VIDEO_BEST_SKILL_MATRIX.md`.
