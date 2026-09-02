from __future__ import annotations

from app.config import get_settings
from app.db.models import PlatformAccount, TopicCandidate
from app.publishing.capabilities import get_capability, resolve_publishing_platform

# media-platform key -> default content type for a topic
_CONTENT_TYPE = {
    "youtube_long": "LONG_VIDEO", "youtube_shorts": "SHORT_VIDEO", "tiktok": "SHORT_VIDEO",
    "instagram_reel": "SHORT_VIDEO", "instagram_carousel": "CAROUSEL",
    "instagram_feed": "SINGLE_IMAGE", "threads": "TEXT_THREAD", "x": "TEXT_THREAD",
    "pinterest": "IMAGE_PIN", "linkedin": "DOCUMENT", "naver_blog": "BLOG_ARTICLE",
}


def _account_ok(session, media_platform: str) -> bool:
    pub_key = resolve_publishing_platform(media_platform)
    acct = (session.query(PlatformAccount)
            .filter(PlatformAccount.platform.in_([media_platform, pub_key])).first())
    if acct is None:
        return False
    return acct.connection_status in ("CONNECTED", "TOKEN_EXPIRING")


def select_platforms(session, cand: TopicCandidate) -> list[dict]:
    """Per-topic platform selection: threshold on the platform score, capability
    + account health check, then a content-type per platform."""
    s = get_settings()
    scores = cand.platform_scores or {}
    chosen: list[dict] = []
    for media_platform, pscore in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
        if not s.autopilot_publish_all_platforms and pscore < s.autopilot_platform_opportunity_threshold:
            continue
        try:
            cap = get_capability(media_platform)
        except KeyError:
            continue
        # honour Phase 2 capability: don't plan public auto-posting where it isn't possible
        note = None
        if cap.publishing_status in ("NOT_SUPPORTED",):
            continue
        if cap.publishing_status in ("MANUAL_ONLY",):
            note = "MANUAL_ONLY"
        elif cap.publishing_status in ("APP_REVIEW_REQUIRED", "ACCOUNT_TYPE_REQUIRED"):
            note = cap.publishing_status
        account_connected = _account_ok(session, media_platform)
        chosen.append({
            "platform": media_platform,
            "platform_score": pscore,
            "content_type": _CONTENT_TYPE.get(media_platform, "SHORT_VIDEO"),
            "account_connected": account_connected,
            "capability_note": note,
        })
    if not chosen and scores:
        best = max(scores, key=scores.get)
        chosen.append({"platform": best, "platform_score": scores[best],
                       "content_type": _CONTENT_TYPE.get(best, "SHORT_VIDEO"),
                       "account_connected": _account_ok(session, best),
                       "capability_note": "below_threshold_fallback"})
    return chosen
