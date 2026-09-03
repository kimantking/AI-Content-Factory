"""Video Skill Router + Quality Profiles + Fallback Ladder (B101, B102, B103, B104).

Given the campaign context, decide which video skills run. Not every skill on
every campaign (no bloat). GPU skills are only 'required' when a GPU worker is
declared available; otherwise they route to their fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.video.registry import VIDEO_SKILLS

QUALITY_PROFILES = ("FAST", "STANDARD", "PREMIUM", "CINEMATIC")


@dataclass
class QualityProfile:
    name: str = "STANDARD"

    @property
    def rank(self) -> int:
        return {"FAST": 0, "STANDARD": 1, "PREMIUM": 2, "CINEMATIC": 3}.get(self.name, 1)


# minimum profile rank at which a skill becomes 'required'
_MIN_RANK = {
    "story_director_v1": 0, "retention_director_v1": 0, "shot_grammar_v1": 0,
    "pacing_engine_v1": 0, "broll_ranker_v1": 1, "cinematic_motion_v1": 1,
    "voice_director_v2": 1, "audio_director_v1": 1, "color_director_v1": 2,
    "timeline_v2": 0, "video_quality_v2": 0, "kinetic_caption_v1": 1,
    "editor_memory_v1": 0, "loudness_qa_v1": 1, "color_stats_probe_v1": 2,
    "vmaf_qa_v1": 3, "segmentation_sam2": 3, "depth_motion_v1": 3,
    "tracking_v1": 2, "diarization_v1": 2, "alignment_whisperx_v1": 2,
    "enhance_esrgan_v1": 3, "interp_rife_v1": 3, "motion_graphics_remotion": 3,
}

FALLBACK_LADDER = {
    "segmentation_sam2": ["tracking_v1", "opencv_saliency_crop", "static_safe_crop"],
    "depth_motion_v1": ["cinematic_motion_v1(DEPTH_PARALLAX_SIM)", "ken_burns"],
    "tracking_v1": ["opencv_basic_tracking", "static_safe_crop"],
    "alignment_whisperx_v1": ["faster_whisper_transcribe", "estimator_alignment"],
    "diarization_v1": ["single_speaker"],
    "motion_graphics_remotion": ["pillow_graphics"],
    "enhance_esrgan_v1": ["skip"],
    "interp_rife_v1": ["skip"],
    "vmaf_qa_v1": ["ssim_estimate", "skip"],
}


@dataclass
class RouteResult:
    profile: str
    required: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)
    fallbacks: dict[str, list[str]] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)


def route(*, platform: str, content_type: str, profile: str = "STANDARD",
          budget_usd: float = 1.0, risk: str = "LOW", opportunity_score: float = 50.0,
          gpu_available: bool = False, is_short: bool = True,
          multi_speaker: bool = False) -> RouteResult:
    qp = QualityProfile(profile if profile in QUALITY_PROFILES else "STANDARD")
    res = RouteResult(profile=qp.name)

    for sid, sk in VIDEO_SKILLS.items():
        min_rank = _MIN_RANK.get(sid, 1)
        want = qp.rank >= min_rank

        # context gates
        if sid == "diarization_v1" and not multi_speaker:
            res.disabled.append(sid)
            res.reasons[sid] = "single-speaker content — diarization skipped"
            continue
        if sid == "kinetic_caption_v1" and not is_short and qp.rank < 2:
            want = False
        if sid in ("vmaf_qa_v1", "segmentation_sam2", "depth_motion_v1",
                   "enhance_esrgan_v1", "interp_rife_v1") and budget_usd < 0.5:
            want = False
            res.reasons.setdefault(sid, "budget below advanced-skill threshold")

        if not want:
            (res.optional if qp.rank + 1 >= min_rank else res.disabled).append(sid)
            res.reasons.setdefault(sid, f"below profile threshold (needs rank {min_rank})")
            continue

        if sk.requires_gpu and not gpu_available:
            res.optional.append(sid)
            res.fallbacks[sid] = FALLBACK_LADDER.get(sid, [sk.fallback or "skip"])
            res.reasons[sid] = "GPU skill without a GPU worker → routed to fallback"
            continue
        if sk.status == "DESIGN_ONLY":
            res.optional.append(sid)
            res.fallbacks[sid] = FALLBACK_LADDER.get(sid, [sk.fallback or "skip"])
            res.reasons[sid] = "DESIGN_ONLY — not executed; fallback used"
            continue

        res.required.append(sid)
        if sk.fallback or sid in FALLBACK_LADDER:
            res.fallbacks[sid] = FALLBACK_LADDER.get(sid, [sk.fallback])

    # CINEMATIC needs budget-allocator approval (B102) — flagged, not enforced here
    if qp.name == "CINEMATIC":
        res.reasons["_profile"] = "CINEMATIC requires budget-allocator approval upstream"
    return res

