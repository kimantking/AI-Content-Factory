from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name("capabilities.json")


class PublishingStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    APP_REVIEW_REQUIRED = "APP_REVIEW_REQUIRED"
    ACCOUNT_TYPE_REQUIRED = "ACCOUNT_TYPE_REQUIRED"
    LIMITED = "LIMITED"
    MANUAL_ONLY = "MANUAL_ONLY"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    UNKNOWN = "UNKNOWN"


class IntegrationStatus(str, Enum):
    CODE_COMPLETE = "CODE_COMPLETE"
    MOCK_TESTED = "MOCK_TESTED"
    REAL_AUTH_TESTED = "REAL_AUTH_TESTED"
    REAL_UPLOAD_TESTED = "REAL_UPLOAD_TESTED"
    REAL_PUBLISH_TESTED = "REAL_PUBLISH_TESTED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass(frozen=True)
class PlatformCapability:
    platform: str
    official_api: str
    auth: str
    required_scopes: list[str]
    publishing_status: str
    auth_supported: bool
    publishing_supported: bool
    video_supported: bool
    image_supported: bool
    carousel_supported: bool
    text_supported: bool
    thread_supported: bool
    schedule_supported: bool
    analytics_supported: bool
    webhook_supported: bool
    app_review_required: bool
    account_requirement: str
    known_limits: str
    implementation_status: str
    implementation_decision: str
    last_verified_at: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def auto_publish_possible(self) -> bool:
        return self.publishing_supported and self.publishing_status not in (
            PublishingStatus.NOT_SUPPORTED.value,
            PublishingStatus.MANUAL_ONLY.value,
        )


@lru_cache
def load_capabilities() -> dict[str, PlatformCapability]:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    verified = raw.get("last_verified_at", "")
    out: dict[str, PlatformCapability] = {}
    fields = set(PlatformCapability.__dataclass_fields__) - {"extra"}
    for row in raw.get("platforms", []):
        known = {k: row[k] for k in fields if k in row}
        known.setdefault("last_verified_at", verified)
        known["extra"] = {k: v for k, v in row.items() if k not in fields}
        out[row["platform"]] = PlatformCapability(**known)
    return out


# media/registry platform keys (Phase 1-B) -> publishing platform keys (Phase 2)
_MEDIA_TO_PUB = {
    "youtube_long": "youtube", "youtube_shorts": "youtube",
    "tiktok": "tiktok",
    "instagram_reel": "instagram", "instagram_feed": "instagram",
    "instagram_carousel": "instagram",
    "facebook_reel": "facebook",
    "threads": "threads", "x": "x",
    "pinterest_image": "pinterest", "pinterest_video": "pinterest",
    "linkedin": "linkedin",
    "naver_blog": "naver_blog", "naver_clip": "naver_clip",
}


def resolve_publishing_platform(platform: str) -> str:
    key = platform.strip().lower()
    if key in load_capabilities():
        return key
    return _MEDIA_TO_PUB.get(key, key)


def get_capability(platform: str) -> PlatformCapability:
    caps = load_capabilities()
    key = resolve_publishing_platform(platform)
    if key not in caps:
        raise KeyError(f"no capability entry for platform {platform!r}")
    return caps[key]
