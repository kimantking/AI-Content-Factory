from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# vocabularies (kept as plain tuples so callers can validate cheaply)
# --------------------------------------------------------------------------- #

STORY_BEATS = (
    "HOOK", "SETUP", "QUESTION", "TENSION", "DISCOVERY", "PROOF", "ESCALATION",
    "CONTRAST", "SURPRISE", "PAYOFF", "SUMMARY", "CTA", "AFTERTHOUGHT",
)
EMOTIONS = (
    "curiosity", "tension", "surprise", "relief", "confidence", "urgency",
    "wonder", "neutral",
)
SHOT_SIZES = (
    "EXTREME_WIDE", "WIDE", "MEDIUM", "MEDIUM_CLOSE", "CLOSE", "EXTREME_CLOSE", "DETAIL",
)
SHOT_PURPOSES = (
    "ESTABLISHING", "CONTEXT", "ACTION", "REACTION", "DETAIL", "PROOF",
    "EMPHASIS", "TRANSITION",
)
MOTION_ENERGY = ("LOW", "MEDIUM", "HIGH")
PRIMARY_FOCUS = ("speaker", "text", "chart", "object", "proof", "action", "scene")
EDIT_INTENTS = (
    "CLARIFY", "EMPHASIZE", "TRANSITION", "ENERGY", "EMOTION", "PROOF",
    "ORIENTATION", "COMEDY", "NONE",
)
BROLL_KINDS = (
    "DIRECT", "CONTEXTUAL", "METAPHORICAL", "ATMOSPHERIC", "PROOF", "PROCESS", "DETAIL",
)
CINEMATIC_MOTIONS = (
    "KEN_BURNS", "DEPTH_PARALLAX_SIM", "DOLLY_IN_SIM", "DOLLY_OUT_SIM",
    "SUBJECT_PUSH", "BACKGROUND_DRIFT", "SLOW_ORBIT_SIM", "FOCUS_PULL_SIM",
    # legacy simple motions still valid
    "SLOW_ZOOM_IN", "SLOW_ZOOM_OUT", "PAN_LEFT", "PAN_RIGHT", "PAN_UP", "PAN_DOWN",
)
TIMEBASES = (23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0)
TRACK_KINDS = (
    "VIDEO_MAIN", "VIDEO_OVERLAY", "GRAPHICS", "CAPTION", "VOICE", "MUSIC", "SFX",
)


# --------------------------------------------------------------------------- #
# per-scene direction
# --------------------------------------------------------------------------- #

@dataclass
class SceneDirection:
    scene_order: int
    story_beat: str = "SETUP"
    emotion_intent: str = "neutral"
    shot_size: str = "MEDIUM"
    shot_purpose: str = "CONTEXT"
    motion_energy: str = "MEDIUM"
    cinematic_motion: str = "KEN_BURNS"
    primary_focus: str = "scene"
    edit_intent: str = "CLARIFY"
    effect_budget: int = 2          # max simultaneous effects allowed this scene
    pattern_interrupt: bool = False
    cognitive_load: float = 0.0     # 0..1
    information_density: float = 0.0  # new-info units / second
    caption_style: str = "CLEAN"
    kinetic_caption: str = "NONE"   # NONE | WORD_REVEAL | NUMBER_PUNCH | ...
    broll_kind: str = "CONTEXTUAL"
    visual_evidence: bool = False   # a source screenshot / chart / real footage would help
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_order": self.scene_order, "story_beat": self.story_beat,
            "emotion_intent": self.emotion_intent, "shot_size": self.shot_size,
            "shot_purpose": self.shot_purpose, "motion_energy": self.motion_energy,
            "cinematic_motion": self.cinematic_motion, "primary_focus": self.primary_focus,
            "edit_intent": self.edit_intent, "effect_budget": self.effect_budget,
            "pattern_interrupt": self.pattern_interrupt, "cognitive_load": round(self.cognitive_load, 3),
            "information_density": round(self.information_density, 3),
            "caption_style": self.caption_style, "kinetic_caption": self.kinetic_caption,
            "broll_kind": self.broll_kind, "visual_evidence": self.visual_evidence,
            "notes": self.notes,
        }


@dataclass
class StoryBeat:
    beat: str
    scene_orders: list[int]
    emotion_from: str
    emotion_to: str
    purpose: str


@dataclass
class VoicePhrasePlan:
    scene_order: int
    text: str
    speed: float = 1.0            # 0.8 slow .. 1.2 fast
    energy: float = 0.5          # 0..1
    emotion: str = "neutral"
    emphasis: list[str] = field(default_factory=list)
    pause_before: float = 0.0
    pause_after: float = 0.12
    pause_after_kind: str = "NONE"   # NONE | BREATH | EMPHASIS | DRAMATIC | UNNECESSARY
    pitch: float = 0.0          # semitone intent, -3..+3
    volume_intent: float = 1.0
    delivery_style: str = "NARRATION"


@dataclass
class VoicePerformancePlan:
    phrases: list[VoicePhrasePlan] = field(default_factory=list)
    consistency_score: float = 1.0
    brand_style: str = "NARRATION"
    notes: list[str] = field(default_factory=list)


@dataclass
class MusicSection:
    label: str          # intro | build | drop | break | outro
    start: float
    end: float
    target_energy: float


@dataclass
class DuckingKeyframe:
    t: float
    music_gain: float   # linear 0..1


@dataclass
class AudioPlan:
    music_sections: list[MusicSection] = field(default_factory=list)
    ducking: list[DuckingKeyframe] = field(default_factory=list)
    sfx_density: float = 0.0            # sfx per 10s
    sfx_density_flag: str = "OK"        # OK | HIGH
    loudness_target_lufs: float = -14.0  # configurable profile target, NOT a claimed platform spec
    true_peak_ceiling_dbtp: float = -1.0
    energy_curve: list[float] = field(default_factory=list)  # per story section, follows arc
    notes: list[str] = field(default_factory=list)


@dataclass
class TimelineClip:
    track: str
    source_ref: str
    start: float
    end: float
    source_in: float = 0.0
    source_out: float = 0.0
    speed: float = 1.0
    opacity: float = 1.0
    crop: tuple[float, float, float, float] | None = None  # x,y,w,h as 0..1
    transform: dict[str, Any] = field(default_factory=dict)
    effects: list[str] = field(default_factory=list)
    intent: str = "NONE"

    @property
    def frame_start(self) -> int:
        return self._fa(self.start)

    @property
    def frame_end(self) -> int:
        return self._fa(self.end)

    _fps: float = 30.0

    def _fa(self, t: float) -> int:
        return int(round(t * self._fps))


@dataclass
class VideoTimeline:
    fps: float = 30.0
    timebase: float = 30.0
    width: int = 1080
    height: int = 1920
    clips: list[TimelineClip] = field(default_factory=list)

    def add(self, clip: TimelineClip) -> None:
        clip._fps = self.fps
        self.clips.append(clip)

    def tracks(self) -> dict[str, list[TimelineClip]]:
        out: dict[str, list[TimelineClip]] = {k: [] for k in TRACK_KINDS}
        for c in self.clips:
            out.setdefault(c.track, []).append(c)
        return out

    @property
    def duration(self) -> float:
        return round(max((c.end for c in self.clips), default=0.0), 3)


@dataclass
class VideoQualityScoreV2:
    dimensions: dict[str, float] = field(default_factory=dict)
    overall: float = 0.0
    weak: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.overall >= 0.62 and not any(v < 0.4 for v in self.dimensions.values())


@dataclass
class VideoCreativePlan:
    """The VideoDirector's output — a full creative brief for one render."""
    platform: str
    content_type: str
    profile: str = "STANDARD"                 # FAST | STANDARD | PREMIUM | CINEMATIC
    story_arc: list[StoryBeat] = field(default_factory=list)
    emotional_arc: list[str] = field(default_factory=list)   # emotion per section
    scene_directions: list[SceneDirection] = field(default_factory=list)
    pace_profile: str = "balanced"
    visual_language: dict[str, Any] = field(default_factory=dict)
    editing_language: dict[str, Any] = field(default_factory=dict)
    shot_language: dict[str, Any] = field(default_factory=dict)
    voice_direction: VoicePerformancePlan = field(default_factory=VoicePerformancePlan)
    sound_direction: AudioPlan = field(default_factory=AudioPlan)
    caption_direction: dict[str, Any] = field(default_factory=dict)
    color_direction: dict[str, Any] = field(default_factory=dict)
    retention_strategy: dict[str, Any] = field(default_factory=dict)
    budget_distribution: dict[int, float] = field(default_factory=dict)  # scene_order -> weight
    high_impact_scenes: list[int] = field(default_factory=list)
    boredom_risk: float = 0.0
    skills: dict[str, str] = field(default_factory=dict)   # skill_id -> required|optional|disabled
    warnings: list[str] = field(default_factory=list)

    def scene(self, order: int) -> SceneDirection | None:
        for d in self.scene_directions:
            if d.scene_order == order:
                return d
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform, "content_type": self.content_type,
            "profile": self.profile, "pace_profile": self.pace_profile,
            "emotional_arc": self.emotional_arc,
            "story_arc": [{"beat": b.beat, "scene_orders": b.scene_orders,
                           "emotion_from": b.emotion_from, "emotion_to": b.emotion_to,
                           "purpose": b.purpose} for b in self.story_arc],
            "scene_directions": [d.to_dict() for d in self.scene_directions],
            "visual_language": self.visual_language,
            "editing_language": self.editing_language,
            "shot_language": self.shot_language,
            "voice_direction": {
                "brand_style": self.voice_direction.brand_style,
                "consistency_score": round(self.voice_direction.consistency_score, 3),
                "phrases": [vars(p) for p in self.voice_direction.phrases],
                "notes": self.voice_direction.notes,
            },
            "sound_direction": {
                "music_sections": [vars(m) for m in self.sound_direction.music_sections],
                "ducking": [vars(k) for k in self.sound_direction.ducking],
                "sfx_density": self.sound_direction.sfx_density,
                "sfx_density_flag": self.sound_direction.sfx_density_flag,
                "loudness_target_lufs": self.sound_direction.loudness_target_lufs,
                "true_peak_ceiling_dbtp": self.sound_direction.true_peak_ceiling_dbtp,
                "energy_curve": self.sound_direction.energy_curve,
                "notes": self.sound_direction.notes,
            },
            "caption_direction": self.caption_direction,
            "color_direction": self.color_direction,
            "retention_strategy": self.retention_strategy,
            "budget_distribution": {str(k): round(v, 4) for k, v in self.budget_distribution.items()},
            "high_impact_scenes": self.high_impact_scenes,
            "boredom_risk": round(self.boredom_risk, 3),
            "skills": self.skills,
            "warnings": self.warnings,
        }
