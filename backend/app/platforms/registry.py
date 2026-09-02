"""Single source of truth for platform-specific media defaults.

Nothing downstream should hard-code a platform string or an aspect ratio — look
it up here. Phase 1-B consumes `PlatformSpec`; Phase 2 will add a `publisher`
capability field to the same rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ContentFamily(str, Enum):
    VIDEO = "VIDEO"
    IMAGE = "IMAGE"
    MIXED = "MIXED"
    TEXT = "TEXT"


class ContentType(str, Enum):
    LONG_VIDEO = "LONG_VIDEO"
    SHORT_VIDEO = "SHORT_VIDEO"
    SINGLE_IMAGE = "SINGLE_IMAGE"
    CAROUSEL = "CAROUSEL"
    IMAGE_PIN = "IMAGE_PIN"
    VIDEO_PIN = "VIDEO_PIN"
    DOCUMENT = "DOCUMENT"
    TEXT_POST = "TEXT_POST"
    TEXT_THREAD = "TEXT_THREAD"
    BLOG_ARTICLE = "BLOG_ARTICLE"


@dataclass(frozen=True)
class PlatformSpec:
    key: str                       # stable id, snake_case
    label: str
    family: ContentFamily
    content_type: ContentType
    aspect_ratio: str              # "W:H"
    target_duration_s: int | None  # None for image/text
    visual_style: str
    subtitle_style: str            # CLEAN | DYNAMIC | DOCUMENTARY | STORY | NEWS | EDUCATIONAL | NONE
    voice_style: str               # NARRATION | CONVERSATIONAL | NONE
    music_style: str               # AMBIENT | UPBEAT | NONE
    thumbnail_required: bool = False
    image_count: int = 0           # >0 for image-centric types
    max_subtitle_lines: int = 2
    storage_dir: str = ""
    publisher_capability: str = "NOT_SUPPORTED"  # Phase 2 fills this in
    extra: dict = field(default_factory=dict)

    def resolution(self) -> tuple[int, int]:
        return ASPECT_RESOLUTION[self.aspect_ratio]


# canonical render resolutions per aspect ratio
ASPECT_RESOLUTION: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "2:3": (1000, 1500),
    "1.91:1": (1200, 628),
}


def _p(**kw) -> PlatformSpec:
    spec = PlatformSpec(**kw)
    if not spec.storage_dir:
        object.__setattr__(spec, "storage_dir", spec.key)
    return spec


PLATFORMS: dict[str, PlatformSpec] = {
    p.key: p
    for p in [
        _p(key="youtube_long", label="YouTube Long", family=ContentFamily.VIDEO,
           content_type=ContentType.LONG_VIDEO, aspect_ratio="16:9", target_duration_s=420,
           visual_style="documentary", subtitle_style="DOCUMENTARY", voice_style="NARRATION",
           music_style="AMBIENT", thumbnail_required=True, max_subtitle_lines=2),
        _p(key="youtube_shorts", label="YouTube Shorts", family=ContentFamily.VIDEO,
           content_type=ContentType.SHORT_VIDEO, aspect_ratio="9:16", target_duration_s=45,
           visual_style="punchy", subtitle_style="DYNAMIC", voice_style="NARRATION",
           music_style="UPBEAT", thumbnail_required=False, max_subtitle_lines=2),
        _p(key="tiktok", label="TikTok", family=ContentFamily.VIDEO,
           content_type=ContentType.SHORT_VIDEO, aspect_ratio="9:16", target_duration_s=40,
           visual_style="fast-cut", subtitle_style="DYNAMIC", voice_style="CONVERSATIONAL",
           music_style="UPBEAT"),
        _p(key="instagram_reel", label="Instagram Reel", family=ContentFamily.VIDEO,
           content_type=ContentType.SHORT_VIDEO, aspect_ratio="9:16", target_duration_s=40,
           visual_style="aesthetic", subtitle_style="STORY", voice_style="CONVERSATIONAL",
           music_style="UPBEAT"),
        _p(key="instagram_feed", label="Instagram Feed", family=ContentFamily.IMAGE,
           content_type=ContentType.SINGLE_IMAGE, aspect_ratio="4:5", target_duration_s=None,
           visual_style="aesthetic", subtitle_style="NONE", voice_style="NONE",
           music_style="NONE", image_count=1),
        _p(key="instagram_carousel", label="Instagram Carousel", family=ContentFamily.IMAGE,
           content_type=ContentType.CAROUSEL, aspect_ratio="4:5", target_duration_s=None,
           visual_style="editorial", subtitle_style="NONE", voice_style="NONE",
           music_style="NONE", image_count=6),
        _p(key="facebook_reel", label="Facebook Reel", family=ContentFamily.VIDEO,
           content_type=ContentType.SHORT_VIDEO, aspect_ratio="9:16", target_duration_s=45,
           visual_style="punchy", subtitle_style="NEWS", voice_style="NARRATION",
           music_style="UPBEAT"),
        _p(key="threads", label="Threads", family=ContentFamily.TEXT,
           content_type=ContentType.TEXT_THREAD, aspect_ratio="1:1", target_duration_s=None,
           visual_style="minimal", subtitle_style="NONE", voice_style="NONE",
           music_style="NONE", image_count=0),
        _p(key="x", label="X", family=ContentFamily.TEXT,
           content_type=ContentType.TEXT_THREAD, aspect_ratio="16:9", target_duration_s=None,
           visual_style="minimal", subtitle_style="NONE", voice_style="NONE",
           music_style="NONE", image_count=0),
        _p(key="pinterest_image", label="Pinterest Image Pin", family=ContentFamily.IMAGE,
           content_type=ContentType.IMAGE_PIN, aspect_ratio="2:3", target_duration_s=None,
           visual_style="infographic", subtitle_style="NONE", voice_style="NONE",
           music_style="NONE", image_count=1),
        _p(key="pinterest_video", label="Pinterest Video Pin", family=ContentFamily.MIXED,
           content_type=ContentType.VIDEO_PIN, aspect_ratio="9:16", target_duration_s=30,
           visual_style="infographic-motion", subtitle_style="EDUCATIONAL",
           voice_style="NARRATION", music_style="AMBIENT"),
        _p(key="linkedin", label="LinkedIn", family=ContentFamily.MIXED,
           content_type=ContentType.DOCUMENT, aspect_ratio="1:1", target_duration_s=60,
           visual_style="professional", subtitle_style="CLEAN", voice_style="NARRATION",
           music_style="NONE", image_count=5),
        _p(key="naver_blog", label="Naver Blog", family=ContentFamily.IMAGE,
           content_type=ContentType.BLOG_ARTICLE, aspect_ratio="1:1", target_duration_s=None,
           visual_style="clean-editorial", subtitle_style="NONE", voice_style="NONE",
           music_style="NONE", image_count=4),
        _p(key="naver_clip", label="Naver Clip", family=ContentFamily.VIDEO,
           content_type=ContentType.SHORT_VIDEO, aspect_ratio="9:16", target_duration_s=40,
           visual_style="punchy", subtitle_style="DYNAMIC", voice_style="NARRATION",
           music_style="UPBEAT"),
    ]
}

ALL_PLATFORMS: list[str] = list(PLATFORMS.keys())

# accept a few human aliases coming from the Phase 1-A dashboard
_ALIASES = {
    "youtube": "youtube_long", "youtube long": "youtube_long",
    "youtube shorts": "youtube_shorts", "shorts": "youtube_shorts",
    "instagram": "instagram_reel", "instagram reels": "instagram_reel",
    "instagram reel": "instagram_reel", "instagram feed": "instagram_feed",
    "instagram carousel": "instagram_carousel", "facebook": "facebook_reel",
    "facebook reels": "facebook_reel", "pinterest": "pinterest_image",
    "naver blog": "naver_blog", "naver clip": "naver_clip",
}


def get_platform(key: str) -> PlatformSpec:
    k = key.strip().lower().replace("-", "_")
    if k in PLATFORMS:
        return PLATFORMS[k]
    if k.replace("_", " ") in _ALIASES:
        return PLATFORMS[_ALIASES[k.replace("_", " ")]]
    if key.strip().lower() in _ALIASES:
        return PLATFORMS[_ALIASES[key.strip().lower()]]
    raise KeyError(f"unknown platform: {key!r}")


def platforms_by_family(family: ContentFamily) -> list[PlatformSpec]:
    return [p for p in PLATFORMS.values() if p.family == family]
