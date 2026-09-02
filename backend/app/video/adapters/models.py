"""CODE_READY interfaces for the GPU/model skills. Each raises
`OptionalSkillUnavailable` unless its dependency is present — never fabricates.
The router routes to a deterministic fallback when these are unavailable.
"""
from __future__ import annotations

from app.video.adapters import OptionalSkillUnavailable, _require


# ---- Subject segmentation (SAM 2, Apache-2.0 code+weights) ---------------- #

def segment_subject(image_path: str, *, prompt_point=None) -> dict:
    _require("sam2", "segmentation_sam2")
    raise OptionalSkillUnavailable(  # pragma: no cover
        "segmentation_sam2",
        "SAM 2 installed but no GPU runtime wired in this build — use opencv_saliency fallback",
    )


# ---- Monocular depth (Depth-Anything-V2; S/B/L weights Apache-2.0) -------- #

def depth_map(image_path: str, *, model_size: str = "small") -> dict:
    if model_size.lower() in ("giant", "g"):
        raise OptionalSkillUnavailable(
            "depth_motion_v1",
            "Depth-Anything-V2 'Giant' weights are CC-BY-NC-4.0 (non-commercial) — blocked; use S/B/L",
        )
    _require("depth_anything_v2", "depth_motion_v1")
    raise OptionalSkillUnavailable(  # pragma: no cover
        "depth_motion_v1", "no GPU runtime in this build — use DEPTH_PARALLAX_SIM fallback")


# ---- Speaker diarization (NeMo / SpeechBrain, Apache-2.0, ungated) -------- #

def diarize(audio_path: str) -> list[dict]:
    for mod in ("nemo", "speechbrain"):
        try:
            _require(mod, "diarization_v1")
            break
        except OptionalSkillUnavailable:
            continue
    else:
        raise OptionalSkillUnavailable(
            "diarization_v1", "install nemo_toolkit or speechbrain (Apache-2.0) for diarization")
    raise OptionalSkillUnavailable(  # pragma: no cover
        "diarization_v1", "diarization backend present but not wired in this build")


# ---- Forced alignment (faster-whisper MIT + WhisperX BSD-2) -------------- #

def align_words(audio_path: str, text: str, *, language: str = "ko") -> list[dict]:
    _require("whisperx", "alignment_whisperx_v1")
    raise OptionalSkillUnavailable(  # pragma: no cover
        "alignment_whisperx_v1",
        "whisperx installed but model download not performed — use estimator alignment")


# ---- Enhancement (Real-ESRGAN BSD-3 code / RIFE MIT code) --------------- #

def upscale(video_or_image_path: str, *, scale: int = 2) -> str:
    _require("realesrgan", "enhance_esrgan_v1")
    raise OptionalSkillUnavailable(  # pragma: no cover
        "enhance_esrgan_v1",
        "Real-ESRGAN code is BSD-3 but verify pretrained-weight dataset terms before commercial use")


def interpolate(video_path: str, *, target_fps: int = 60) -> str:
    _require("rife", "interp_rife_v1")
    raise OptionalSkillUnavailable(  # pragma: no cover
        "interp_rife_v1", "RIFE code is MIT; some model weights are non-commercial — verify weights")
