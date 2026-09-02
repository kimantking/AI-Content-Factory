from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class VisualType(str, Enum):
    AI_VIDEO = "AI_VIDEO"
    AI_IMAGE = "AI_IMAGE"
    STOCK_VIDEO = "STOCK_VIDEO"
    MOTION_GRAPHIC = "MOTION_GRAPHIC"
    TEXT_CARD = "TEXT_CARD"
    CHART = "CHART"
    SCREENSHOT = "SCREENSHOT"
    BACKGROUND = "BACKGROUND"
    NONE = "NONE"


# cost-aware fallback order for a scene that cannot get its first-choice visual
VISUAL_FALLBACK: dict[str, list[str]] = {
    VisualType.AI_VIDEO: [VisualType.STOCK_VIDEO, VisualType.AI_IMAGE, VisualType.MOTION_GRAPHIC, VisualType.TEXT_CARD],
    VisualType.STOCK_VIDEO: [VisualType.AI_IMAGE, VisualType.MOTION_GRAPHIC, VisualType.TEXT_CARD],
    VisualType.AI_IMAGE: [VisualType.MOTION_GRAPHIC, VisualType.TEXT_CARD],
    VisualType.MOTION_GRAPHIC: [VisualType.TEXT_CARD],
    VisualType.CHART: [VisualType.TEXT_CARD],
    VisualType.TEXT_CARD: [VisualType.BACKGROUND],
}


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRY = "RETRY"
    FALLBACK = "FALLBACK"
    CANCELLED = "CANCELLED"


class ProviderMode(str, Enum):
    REAL = "REAL"
    MOCK = "MOCK"
    DISABLED = "DISABLED"
    ERROR = "ERROR"


class ImagePromptSpec(BaseModel):
    subject: str = ""
    environment: str = ""
    action: str = ""
    composition: str = ""
    camera: str = ""
    lighting: str = ""
    style: str = ""
    mood: str = ""
    background: str = ""
    text_safe_area: str = ""
    negative_prompt: str = ""

    def to_prompt(self) -> str:
        parts = [self.subject, self.action, self.environment, self.background,
                 self.composition, self.camera, self.lighting, self.style, self.mood]
        return ", ".join(p.strip() for p in parts if p and p.strip())


class CharacterProfile(BaseModel):
    consistency_id: str
    appearance: str = ""
    approx_age: str = ""
    hair: str = ""
    clothing: str = ""
    visual_style: str = ""


class WordTiming(BaseModel):
    word: str
    start: float
    end: float


class SubtitleBlock(BaseModel):
    start: float
    end: float
    text: str
    position: str = "bottom"
    font_size: int = 48
    highlight_words: list[str] = Field(default_factory=list)
    animation: str = "none"          # none | fade | pop | karaoke
    max_lines: int = 2


class SceneSpec(BaseModel):
    scene_order: int
    narration: str
    estimated_duration: float
    start_time: float = 0.0
    end_time: float = 0.0
    visual_type: VisualType = VisualType.AI_IMAGE
    visual_description: str = ""
    visual_prompt: ImagePromptSpec = Field(default_factory=ImagePromptSpec)
    negative_prompt: str = ""
    source_ids: list[str] = Field(default_factory=list)
    camera_motion: str = "SLOW_ZOOM_IN"
    motion_effect: str = ""
    transition: str = "CUT"
    subtitle_text: str = ""
    highlight_words: list[str] = Field(default_factory=list)
    sound_effect: str = ""
    music_energy: str = "mid"
    consistency_id: str | None = None


class EditDecision(BaseModel):
    scene_id: str
    scene_order: int
    clip_start: float = 0.0
    clip_end: float = 0.0
    speed: float = 1.0
    zoom: float = 1.08
    transition: str = "CUT"
    subtitle_style: str = "CLEAN"
    music_volume: float = 0.18
    voice_volume: float = 1.0
    sfx: list[str] = Field(default_factory=list)


class ChartSpec(BaseModel):
    chart_type: str = "bar"          # bar | line | pie
    title: str = ""
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ThumbnailConcept(BaseModel):
    headline: str
    visual_subject: str
    emotion: str = ""
    composition: str = ""
    background: str = ""
    contrast_strategy: str = ""
    scores: dict[str, float] = Field(default_factory=dict)


class CarouselPage(BaseModel):
    page_number: int
    headline: str
    body: str = ""
    visual_prompt: str = ""
    layout_type: str = "text-over-image"


class PlatformContentSpec(BaseModel):
    platform: str
    content_type: str
    hook: str = ""
    script: str = ""
    cta: str = ""
    title: str = ""
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    target_duration: int | None = None
    aspect_ratio: str = "9:16"
    visual_style: str = ""
    subtitle_style: str = ""
    voice_style: str = ""
    music_style: str = ""
    thumbnail_required: bool = False
    image_count: int = 0
