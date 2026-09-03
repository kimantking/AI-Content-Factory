"""Video Skill Registry + versioning (B95, B96).

Metadata for every video skill so the router can gate it and Phase-3 Analytics can
later attribute retention/engagement to a skill *version*. This is a plain table,
not a framework.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoSkill:
    skill_id: str
    name: str
    version: str
    category: str
    requires_llm: bool = False
    requires_gpu: bool = False
    algorithm: str = ""
    dependencies: tuple[str, ...] = ()
    fallback: str | None = None
    quality_impact: str = "medium"     # low | medium | high
    cost_impact: str = "low"
    latency_impact: str = "low"
    enabled: bool = True
    status: str = "IMPLEMENTED"        # IMPLEMENTED | CODE_READY | DESIGN_ONLY


VIDEO_SKILLS: dict[str, VideoSkill] = {
    s.skill_id: s for s in [
        VideoSkill("story_director_v1", "Story Director", "1", "creative",
                   algorithm="beat-cue mapping + emotion arc", quality_impact="high"),
        VideoSkill("retention_director_v1", "Retention Director", "1", "creative",
                   algorithm="checkpoint + open-loop + boredom scan", quality_impact="high"),
        VideoSkill("shot_grammar_v1", "Shot Grammar Engine", "1", "visual",
                   algorithm="beat→size/purpose + repetition break", quality_impact="high"),
        VideoSkill("pacing_engine_v1", "Pacing Engine", "1", "editing",
                   algorithm="visual refresh + info density + cognitive load", quality_impact="high"),
        VideoSkill("broll_ranker_v1", "B-roll Director", "1", "visual",
                   algorithm="9-axis score + kind classification", quality_impact="high",
                   fallback="keyword_stock_search"),
        VideoSkill("cinematic_motion_v1", "Cinematic Image Motion", "1", "visual",
                   algorithm="ffmpeg zoompan/parallax-sim builders", quality_impact="medium",
                   fallback="ken_burns"),
        VideoSkill("voice_director_v2", "Voice Director V2", "2", "audio",
                   algorithm="per-phrase prosody plan + consistency", quality_impact="medium"),
        VideoSkill("audio_director_v1", "Audio Director", "1", "audio",
                   algorithm="music-structure + ducking envelope + sfx density", quality_impact="medium"),
        VideoSkill("color_director_v1", "Color Director", "1", "finish",
                   algorithm="pillow stats + median match plan", quality_impact="low",
                   fallback="no_grade"),
        VideoSkill("timeline_v2", "Edit Decision V2 / Timeline", "2", "editing",
                   algorithm="frame-accurate multi-track non-destructive", quality_impact="medium"),
        VideoSkill("video_quality_v2", "Video Quality Score V2", "2", "qa",
                   algorithm="16-dim weighted", quality_impact="medium"),
        VideoSkill("kinetic_caption_v1", "Kinetic Typography", "1", "caption",
                   algorithm="ASS \\k karaoke + effect templates", quality_impact="medium",
                   fallback="static_caption"),
        VideoSkill("editor_memory_v1", "Editor Memory", "1", "creative",
                   algorithm="recent-choices repetition avoidance", quality_impact="medium"),
        VideoSkill("loudness_qa_v1", "Loudness QA", "1", "qa",
                   algorithm="ffmpeg ebur128", dependencies=("ffmpeg-ebur128",),
                   quality_impact="medium", status="CODE_READY"),
        VideoSkill("color_stats_probe_v1", "Color Stats Probe", "1", "qa",
                   algorithm="ffmpeg signalstats", dependencies=("ffmpeg-signalstats",),
                   quality_impact="low", status="CODE_READY"),
        VideoSkill("vmaf_qa_v1", "VMAF QA", "1", "qa",
                   algorithm="ffmpeg libvmaf (BSD+Patent)", dependencies=("ffmpeg-libvmaf",),
                   quality_impact="low", status="CODE_READY"),
        # GPU / model adapters — CODE_READY, never faked
        VideoSkill("segmentation_sam2", "Subject Segmentation (SAM 2)", "1", "visual",
                   requires_gpu=True, algorithm="SAM 2 (Apache-2.0)",
                   dependencies=("sam2", "torch"), fallback="opencv_saliency_crop",
                   quality_impact="high", status="CODE_READY"),
        VideoSkill("depth_motion_v1", "Depth Parallax (Depth-Anything-V2)", "1", "visual",
                   requires_gpu=True, algorithm="Depth-Anything-V2 S/B/L weights Apache-2.0",
                   dependencies=("depth-anything-v2", "torch"), fallback="depth_parallax_sim",
                   quality_impact="medium", status="CODE_READY"),
        VideoSkill("tracking_v1", "Subject Tracking", "1", "visual",
                   algorithm="OpenCV trackers (Apache-2.0); CoTracker REFERENCE_ONLY (non-commercial)",
                   dependencies=("opencv-python",), fallback="static_safe_crop",
                   quality_impact="medium", status="CODE_READY"),
        VideoSkill("diarization_v1", "Speaker Diarization", "1", "audio",
                   requires_gpu=True, algorithm="NeMo / SpeechBrain (Apache-2.0, ungated)",
                   dependencies=("nemo_toolkit",), fallback="single_speaker",
                   quality_impact="medium", status="CODE_READY"),
        VideoSkill("alignment_whisperx_v1", "Forced Alignment (WhisperX)", "1", "audio",
                   requires_gpu=False, algorithm="faster-whisper (MIT) + WhisperX (BSD-2)",
                   dependencies=("whisperx",), fallback="estimator_alignment",
                   quality_impact="high", status="CODE_READY"),
        VideoSkill("enhance_esrgan_v1", "Upscale (Real-ESRGAN)", "1", "restore",
                   requires_gpu=True, algorithm="Real-ESRGAN (BSD-3 code; verify weight terms)",
                   dependencies=("realesrgan", "torch"), fallback="none",
                   quality_impact="low", status="CODE_READY"),
        VideoSkill("interp_rife_v1", "Frame Interpolation (RIFE)", "1", "restore",
                   requires_gpu=True, algorithm="RIFE (MIT code; some weights non-commercial)",
                   dependencies=("rife",), fallback="none",
                   quality_impact="low", status="CODE_READY"),
        VideoSkill("motion_graphics_remotion", "Motion Graphics (Remotion)", "1", "graphics",
                   algorithm="Remotion (source-available, company licence ≥4 employees)",
                   dependencies=("node", "remotion"), fallback="pillow_graphics",
                   quality_impact="high", status="DESIGN_ONLY"),
    ]
}


def get_skill(skill_id: str) -> VideoSkill | None:
    return VIDEO_SKILLS.get(skill_id)


def skills_by_status(status: str) -> list[VideoSkill]:
    return [s for s in VIDEO_SKILLS.values() if s.status == status]
