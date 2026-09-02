from __future__ import annotations

from app.analytics.base import Availability, MetricValue
from app.analytics.capabilities import get_analytics_capability

# api_metric_name -> (normalized_name, unit, scale, aggregation)
# Metric names are never hard-coded at call sites — everything routes through here.
_MAP: dict[str, dict[str, tuple[str, str, float, str]]] = {
    "youtube": {
        "views": ("views", "count", 1, "cumulative"),
        "estimatedMinutesWatched": ("watch_time_seconds", "seconds", 60, "cumulative"),
        "averageViewDuration": ("avg_watch_duration_seconds", "seconds", 1, "average"),
        "averageViewPercentage": ("avg_view_percentage", "percent", 1, "average"),
        "likes": ("likes", "count", 1, "cumulative"),
        "comments": ("comments", "count", 1, "cumulative"),
        "shares": ("shares", "count", 1, "cumulative"),
        "subscribersGained": ("subscribers_gained", "count", 1, "cumulative"),
        "cardImpressions": ("impressions", "count", 1, "cumulative"),
        "cardClickRate": ("ctr", "ratio", 1, "average"),
        "estimatedRevenue": ("estimated_revenue", "currency", 1, "cumulative"),
    },
    "tiktok": {
        "views": ("views", "count", 1, "cumulative"),
        "likes": ("likes", "count", 1, "cumulative"),
        "comments": ("comments", "count", 1, "cumulative"),
        "shares": ("shares", "count", 1, "cumulative"),
        "followers_gained": ("followers_gained", "count", 1, "cumulative"),
    },
    "instagram": {
        "views": ("views", "count", 1, "cumulative"),
        "reach": ("reach", "count", 1, "cumulative"),
        "likes": ("likes", "count", 1, "cumulative"),
        "comments": ("comments", "count", 1, "cumulative"),
        "shares": ("shares", "count", 1, "cumulative"),
        "saves": ("saves", "count", 1, "cumulative"),
        "reposts": ("reposts", "count", 1, "cumulative"),
    },
    "facebook": {
        "impressions": ("impressions", "count", 1, "cumulative"),
        "reach": ("reach", "count", 1, "cumulative"),
        "views": ("views", "count", 1, "cumulative"),
        "likes": ("likes", "count", 1, "cumulative"),
        "comments": ("comments", "count", 1, "cumulative"),
        "shares": ("shares", "count", 1, "cumulative"),
        "watch_time_seconds": ("watch_time_seconds", "seconds", 1, "cumulative"),
        "avg_watch_duration_seconds": ("avg_watch_duration_seconds", "seconds", 1, "average"),
    },
    "threads": {
        "views": ("views", "count", 1, "cumulative"),
        "likes": ("likes", "count", 1, "cumulative"),
        "comments": ("comments", "count", 1, "cumulative"),
        "reposts": ("reposts", "count", 1, "cumulative"),
        "quotes": ("quotes", "count", 1, "cumulative"),
        "shares": ("shares", "count", 1, "cumulative"),
    },
    "x": {
        "likes": ("likes", "count", 1, "cumulative"),
        "comments": ("comments", "count", 1, "cumulative"),
        "reposts": ("reposts", "count", 1, "cumulative"),
        "quotes": ("quotes", "count", 1, "cumulative"),
        "bookmarks": ("bookmarks", "count", 1, "cumulative"),
        "impressions": ("impressions", "count", 1, "cumulative"),
        "views": ("views", "count", 1, "cumulative"),
    },
    "pinterest": {
        "impressions": ("impressions", "count", 1, "cumulative"),
        "saves": ("saves", "count", 1, "cumulative"),
        "link_clicks": ("link_clicks", "count", 1, "cumulative"),
        "views": ("views", "count", 1, "cumulative"),
        "avg_watch_duration_seconds": ("avg_watch_duration_seconds", "seconds", 1, "average"),
    },
    "linkedin": {
        "impressions": ("impressions", "count", 1, "cumulative"),
        "link_clicks": ("link_clicks", "count", 1, "cumulative"),
        "likes": ("likes", "count", 1, "cumulative"),
        "comments": ("comments", "count", 1, "cumulative"),
        "shares": ("shares", "count", 1, "cumulative"),
        "views": ("views", "count", 1, "cumulative"),
    },
    "naver_blog": {"views": ("views", "count", 1, "cumulative"),
                   "link_clicks": ("link_clicks", "count", 1, "cumulative")},
    "naver_clip": {"views": ("views", "count", 1, "cumulative"),
                   "likes": ("likes", "count", 1, "cumulative")},
}

# normalized names that live as columns on analytics_snapshots
NORMALIZED_COLUMNS = [
    "views", "impressions", "reach", "likes", "comments", "shares", "saves",
    "reposts", "bookmarks", "quotes", "watch_time_seconds",
    "avg_watch_duration_seconds", "avg_view_percentage", "completion_rate", "ctr",
    "followers_gained", "subscribers_gained", "profile_visits", "link_clicks",
    "estimated_revenue",
]


def platform_map(platform: str) -> dict:
    return _MAP.get(platform, {})


def normalize(platform: str, raw: dict) -> dict[str, MetricValue]:
    """RAW api dict -> {normalized_name: MetricValue}. Capability decides the
    availability; a value the API cannot give is None + a status, never 0."""
    cap = get_analytics_capability(platform)
    pm = platform_map(platform)
    out: dict[str, MetricValue] = {}
    for api_name, (norm, unit, scale, _agg) in pm.items():
        avail = cap.availability(api_name)
        val = raw.get(api_name)
        if avail != Availability.AVAILABLE:
            out[norm] = MetricValue(normalized_name=norm, value=None, availability=avail,
                                    unit=unit, raw_name=api_name)
        elif val is None:
            out[norm] = MetricValue(normalized_name=norm, value=None,
                                    availability=Availability.NOT_READY, unit=unit, raw_name=api_name)
        else:
            out[norm] = MetricValue(normalized_name=norm, value=float(val) * scale,
                                    availability=Availability.AVAILABLE, unit=unit, raw_name=api_name)

    # capability lists a metric the platform_map doesn't wire (e.g. TikTok
    # watch_time_seconds = UNAVAILABLE) -> still record its status, never 0.
    for cap_metric, status in cap.metrics.items():
        if cap_metric in NORMALIZED_COLUMNS and cap_metric not in out:
            out[cap_metric] = MetricValue(
                normalized_name=cap_metric, value=None,
                availability=Availability(status), raw_name=cap_metric,
            )
    return out


def seed_catalog(session) -> int:
    """Idempotently populate metric_catalog."""
    from app.db.models import MetricDef

    existing = {(m.platform, m.api_metric_name) for m in session.query(MetricDef).all()}
    n = 0
    for platform, pm in _MAP.items():
        cap = get_analytics_capability(platform)
        for api_name, (norm, unit, _scale, agg) in pm.items():
            if (platform, api_name) in existing:
                continue
            session.add(MetricDef(
                metric_id=f"{platform}:{api_name}", platform=platform,
                api_metric_name=api_name, normalized_name=norm, unit=unit,
                content_types=[], availability=cap.availability(api_name).value,
                aggregation_type=agg, last_verified_at=cap.last_verified_at,
            ))
            n += 1
    session.flush()
    return n
