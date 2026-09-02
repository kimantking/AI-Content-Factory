"""Advanced Video Studio — deterministic creative-direction layer (Video Studio Upgrade).

A team of "Directors" that plan a video the way an editorial team would:
story arc, retention design, shot grammar, pacing, B-roll intent, cinematic
motion, voice performance, sound design, colour, a non-destructive timeline, a
multi-dimension quality score, and a router that decides which of these skills
run for a given campaign/profile.

Almost everything here is a pure/deterministic Engine — no LLM call, no new heavy
dependency. GPU/model-backed skills (segmentation, depth, tracking, diarization,
enhancement, VMAF) live in `app.video.adapters` as CODE_READY optional adapters
that raise `OptionalSkillUnavailable` rather than fake a result.

Design + OSS comparison: docs/VIDEO_ARCHITECTURE.md, docs/VIDEO_BEST_SKILL_MATRIX.md
"""
from __future__ import annotations

from app.video.director import VideoDirector, direct_video
from app.video.registry import VIDEO_SKILLS, VideoSkill
from app.video.router import QualityProfile, VideoSkillRouter, route_video_skills
from app.video.schema import (
    AudioPlan,
    SceneDirection,
    StoryBeat,
    VideoCreativePlan,
    VideoQualityScoreV2,
    VoicePerformancePlan,
)

# extended engines (Video Studio Upgrade — continuation)
from app.video import captions, creative_qa, cuts, rerender, technical_qa  # noqa: F401

__all__ = [
    "VideoDirector",
    "direct_video",
    "VideoCreativePlan",
    "SceneDirection",
    "StoryBeat",
    "AudioPlan",
    "VoicePerformancePlan",
    "VideoQualityScoreV2",
    "VideoSkillRouter",
    "route_video_skills",
    "QualityProfile",
    "VIDEO_SKILLS",
    "VideoSkill",
    "cuts",
    "captions",
    "creative_qa",
    "rerender",
    "technical_qa",
]
