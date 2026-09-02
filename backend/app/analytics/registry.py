from __future__ import annotations

from app.analytics.providers import (
    FacebookAnalyticsProvider,
    InstagramAnalyticsProvider,
    LinkedInAnalyticsProvider,
    NaverAnalyticsProvider,
    PinterestAnalyticsProvider,
    ThreadsAnalyticsProvider,
    TikTokAnalyticsProvider,
    XAnalyticsProvider,
    YouTubeAnalyticsProvider,
)
from app.publishing.capabilities import resolve_publishing_platform

_REGISTRY = {
    "youtube": YouTubeAnalyticsProvider, "tiktok": TikTokAnalyticsProvider,
    "instagram": InstagramAnalyticsProvider, "facebook": FacebookAnalyticsProvider,
    "threads": ThreadsAnalyticsProvider, "x": XAnalyticsProvider,
    "pinterest": PinterestAnalyticsProvider, "linkedin": LinkedInAnalyticsProvider,
    "naver_blog": NaverAnalyticsProvider, "naver_clip": NaverAnalyticsProvider,
}


def get_analytics_provider(platform: str, client=None):
    key = platform.strip().lower()
    if key not in _REGISTRY:
        key = resolve_publishing_platform(key)
    if key not in _REGISTRY:
        raise KeyError(f"no analytics provider for platform {platform!r}")
    return _REGISTRY[key](client)


def all_analytics_platforms() -> list[str]:
    return list(_REGISTRY)
