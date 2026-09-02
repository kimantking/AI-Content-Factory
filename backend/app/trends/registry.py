from __future__ import annotations

from app.trends.capabilities import load_trend_capabilities
from app.trends.providers import (
    GoogleTrendProvider,
    NaverTrendProvider,
    NewsTrendProvider,
    OwnAnalyticsTrendProvider,
    RedditTrendProvider,
    ThreadsTrendProvider,
    TikTokTrendProvider,
    WebSearchTrendProvider,
    XTrendProvider,
    YouTubeTrendProvider,
)

_REGISTRY = {
    "youtube_most_popular": YouTubeTrendProvider,
    "google_trends": GoogleTrendProvider,
    "web_search": WebSearchTrendProvider,
    "news_search": NewsTrendProvider,
    "naver_datalab": NaverTrendProvider,
    "reddit_signal": RedditTrendProvider,
    "own_analytics": OwnAnalyticsTrendProvider,
    "tiktok_trends": TikTokTrendProvider,
    "threads_trends": ThreadsTrendProvider,
    "x_trends": XTrendProvider,
}


def get_trend_provider(source_id: str, client=None):
    if source_id not in _REGISTRY:
        raise KeyError(f"no trend provider for {source_id!r}")
    return _REGISTRY[source_id](client)


def all_trend_sources() -> list[str]:
    return list(_REGISTRY)


def seed_trend_sources(session) -> int:
    """Idempotently populate trend_sources from the capability registry."""
    from app.db.models import TrendSource

    have = {t.source_id for t in session.query(TrendSource).all()}
    n = 0
    for sid, cap in load_trend_capabilities().items():
        if sid in have:
            continue
        session.add(TrendSource(
            source_id=sid, name=cap.name, source_type=cap.source_type, provider=cap.provider,
            enabled=cap.auth_status in ("AVAILABLE", "AUTH_REQUIRED"),
            auth_status=cap.auth_status, reliability=cap.reliability, cost=cap.cost,
            freshness=cap.freshness, health="UNKNOWN", value_score=cap.reliability,
            meta={"known_limitations": cap.known_limitations,
                  "last_verified_at": cap.last_verified_at},
        ))
        n += 1
    session.flush()
    return n
