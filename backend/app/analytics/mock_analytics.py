from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone

from app.analytics.base import Availability, MetricValue, PostMetrics
from app.analytics.capabilities import get_analytics_capability
from app.analytics.faults import analytics_faults
from app.analytics.metric_catalog import normalize, platform_map


def _seed(s: str) -> float:
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _age_curve(minutes: int) -> float:
    # saturating growth: ~0 at t=0, ~1 by ~30 days
    return 1.0 - math.exp(-minutes / (60 * 24 * 6))


def synth_raw(platform: str, remote_post_id: str, *, content_age_minutes: int,
              feature_hint: dict | None = None) -> dict:
    """Deterministic, feature-driven raw metrics for the mock. Signal is baked in
    so the Learning Engine has real (mock) patterns to find; correlation only."""
    fh = feature_hint or {}
    r = _seed(remote_post_id)
    r2 = _seed(remote_post_id[::-1])
    grow = _age_curve(content_age_minutes)

    base = {"youtube": 4000, "tiktok": 9000, "instagram": 3000, "facebook": 2000,
            "threads": 1500, "x": 1200, "pinterest": 2500, "linkedin": 800,
            "naver_blog": 600, "naver_clip": 1800}.get(platform, 1500)
    views = base * (0.4 + 1.6 * r) * (0.15 + 0.85 * grow)

    # small deterministic per-post noise (kept modest so the baked-in signal
    # dominates and learning is not flaky)
    eng = 0.05 + 0.012 * r2
    retention = 0.45 + 0.06 * r2
    # --- baked-in signal knobs (mock only; correlation, not causation) ---
    if fh.get("hook_type") == "WARNING":
        eng *= 1.30
        views *= 1.10
    dur = fh.get("video_duration") or 0
    if 60 <= dur <= 85:
        retention *= 1.35
        views *= 1.12
    if (fh.get("ai_video_ratio") or 0) > 0.30:
        retention *= 0.75
    if (fh.get("ai_slop_score") or 100) < 15:
        retention *= 1.20
    if (fh.get("scene_duration_variance") or 0) > 1.0:
        views *= 1.15
    comments_boost = 1.25 if fh.get("cta_type") == "QUESTION" else 1.0
    ph = fh.get("publish_hour")
    if ph is not None and 18 <= ph <= 21:
        views *= 1.18

    views = round(views)
    likes = round(views * eng * (0.55 + 0.4 * r))
    comments = round(views * eng * 0.12 * comments_boost)
    shares = round(views * eng * 0.08)
    saves = round(views * eng * 0.10)
    reposts = round(views * eng * 0.05)
    quotes = round(views * eng * 0.02)
    bookmarks = round(views * eng * 0.06)
    reach = round(views * (1.1 + 0.3 * r))
    impressions = round(views * (1.3 + 0.5 * r))
    wt_per_view = max(4.0, dur * retention) if dur else 12.0 * retention
    watch_time = round(views * wt_per_view)
    avg_dur = round(wt_per_view, 2)
    avg_pct = round(min(0.98, retention) * 100, 2)
    followers = round(views * 0.004 * (0.5 + r))
    subs = followers
    link_clicks = round(views * 0.015)

    return {
        # superset of every platform's api metric names (normalize() filters by capability)
        "views": views, "estimatedMinutesWatched": watch_time / 60,
        "averageViewDuration": avg_dur, "averageViewPercentage": avg_pct,
        "likes": likes, "comments": comments, "shares": shares,
        "subscribersGained": subs, "cardImpressions": impressions,
        "cardClickRate": round(0.03 + 0.02 * r, 4),
        "estimatedRevenue": None,                       # not monetized in mock
        "followers_gained": followers,
        "reach": reach, "saves": saves, "reposts": reposts, "quotes": quotes,
        "bookmarks": bookmarks, "impressions": impressions,
        "watch_time_seconds": watch_time,
        "avg_watch_duration_seconds": avg_dur,
        "link_clicks": link_clicks,
    }


class MockAnalyticsClient:
    mode = "MOCK"

    def fetch(self, platform: str, remote_post_id: str, *, content_age_minutes: int,
              feature_hint: dict | None = None) -> dict:
        analytics_faults.maybe_raise(platform)
        return synth_raw(platform, remote_post_id, content_age_minutes=content_age_minutes,
                         feature_hint=feature_hint)

    def account(self, platform: str, account_id: str) -> dict:
        analytics_faults.maybe_raise(platform)
        r = _seed(account_id)
        return {"followers": round(50000 * (0.2 + r)), "following": 120,
                "posts": round(80 + 200 * r)}

    def audience(self, platform: str, account_id: str) -> dict:
        # aggregate only — no PII
        return {"top_country": "KR", "age_band_top": "25-34", "gender_split": {"f": 0.52, "m": 0.48}}


def build_post_metrics(platform: str, remote_post_id: str, *, content_type: str,
                       content_age_minutes: int, window_label: str,
                       raw: dict, provider: str, provider_mode: str) -> PostMetrics:
    metrics = normalize(platform, raw)

    # NOT_APPLICABLE for content types that can't have the metric
    if content_type.upper() in ("SINGLE_IMAGE", "CAROUSEL", "IMAGE_PIN", "TEXT_POST", "TEXT_THREAD"):
        for k in ("watch_time_seconds", "avg_watch_duration_seconds", "avg_view_percentage",
                  "completion_rate"):
            if k in metrics:
                metrics[k] = MetricValue(normalized_name=k, value=None,
                                         availability=Availability.NOT_APPLICABLE, unit="seconds")

    usable = sum(1 for m in metrics.values() if m.usable)
    total_expected = len(platform_map(platform))
    status = ("SUCCESS" if usable >= total_expected
              else "PARTIAL" if usable > 0 else "UNAVAILABLE")
    return PostMetrics(
        platform=platform, remote_post_id=remote_post_id,
        collected_at=datetime.now(timezone.utc).isoformat(),
        content_age_minutes=content_age_minutes, window_label=window_label,
        data_source="PLATFORM_API", provider=provider, provider_mode=provider_mode,
        collection_status=status, metrics=metrics, raw_payload=raw,
    )
