from __future__ import annotations

from dataclasses import dataclass, field

from app.db.models import Asset, Campaign, Publication, PublishJob
from app.media.ffmpeg import probe
from app.platforms import get_platform
from app.providers.media import get_storage
from app.publishing.capabilities import get_capability
from app.publishing.token_manager import CONNECTED, TOKEN_EXPIRING, connection_state
from datetime import datetime, timedelta, timezone
from sqlalchemy import func

# Conservative platform limits. VERIFY against official docs at implementation
# time — treated as guardrails, not gospel. Missing entry => generic caps.
LIMITS: dict[str, dict] = {
    "youtube": {"title": 100, "description": 5000, "caption": 5000, "posts_24h": 100},
    "youtube_shorts": {"title": 100, "description": 5000, "posts_24h": 100},
    "tiktok": {"title": 2200, "caption": 2200, "video_max_s": 600},
    "instagram": {"caption": 2200, "posts_24h": 100, "reel_min_s": 3, "reel_max_s": 90},
    "instagram_reel": {"caption": 2200, "posts_24h": 100},
    "instagram_feed": {"caption": 2200, "posts_24h": 100},
    "instagram_carousel": {"caption": 2200, "posts_24h": 100, "carousel_max": 10},
    "facebook": {"caption": 63206},
    "facebook_reel": {"caption": 2200},
    "threads": {"caption": 500, "posts_24h": 250, "video_max_s": 300, "carousel_max": 10},
    "x": {"caption": 280},
    "pinterest": {"title": 100, "description": 800},
    "pinterest_image": {"title": 100, "description": 800},
    "pinterest_video": {"title": 100, "description": 800},
    "linkedin": {"caption": 3000},
    "naver_blog": {"title": 100},
}
_GENERIC = {"title": 150, "caption": 2200, "description": 5000}


@dataclass
class PreflightReport:
    ok: bool
    checks: dict[str, bool] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


def _limit(platform: str, key: str, default: int) -> int:
    return LIMITS.get(platform, {}).get(key, _GENERIC.get(key, default))


def run_preflight(session, job: PublishJob) -> PreflightReport:
    checks: dict[str, bool] = {}
    issues: list[str] = []
    plat = job.platform
    cap = get_capability(plat)

    # 1. media files
    assets = {a.id: a for a in session.query(Asset).filter(Asset.id.in_(job.media_asset_ids or []))}
    checks["media_listed"] = bool(job.media_asset_ids)
    if not job.media_asset_ids and cap.publishing_supported and plat not in ("naver_blog",):
        issues.append("no media assets on job")
    stg = get_storage()
    readable = True
    total_dur = None
    w = h = None
    for aid in job.media_asset_ids or []:
        a = assets.get(aid)
        if not a or not stg.exists(a.storage_path):
            readable = False
            issues.append(f"media missing/unreadable: {aid}")
            continue
        if a.asset_type in ("render", "video") and a.storage_path.endswith((".mp4", ".mov")):
            info = probe(a.storage_path)
            total_dur = info.get("duration")
            w, h = info.get("width"), info.get("height")
            checks["has_video_stream"] = info.get("has_video", False)
            checks["has_audio_stream"] = info.get("has_audio", False)
    checks["media_readable"] = readable

    # 2. duration / aspect vs platform spec
    try:
        pspec = get_platform(plat)
        ew, eh = pspec.resolution()
        if w and h:
            checks["aspect_ok"] = abs((w / h) - (ew / eh)) < 0.03
            if not checks["aspect_ok"]:
                issues.append(f"aspect {w}x{h} != platform {ew}x{eh} (normalizer can fix)")
        if total_dur is not None:
            vmax = _limit(plat, "video_max_s", 3600)
            checks["duration_ok"] = total_dur <= vmax
            if not checks["duration_ok"]:
                issues.append(f"video {total_dur:.0f}s exceeds {vmax}s")
    except KeyError:
        pass

    # 3. text lengths
    checks["title_len_ok"] = len(job.title or "") <= _limit(plat, "title", 150)
    checks["caption_len_ok"] = len(job.caption or "") <= _limit(plat, "caption", 2200)
    checks["description_len_ok"] = len(job.description or "") <= _limit(plat, "description", 5000)
    for k in ("title_len_ok", "caption_len_ok", "description_len_ok"):
        if not checks[k]:
            issues.append(k.replace("_ok", " exceeds platform limit"))

    # 4. QA + compliance (from Phase 1-B)
    camp = session.get(Campaign, job.campaign_id)
    checks["campaign_ok"] = camp is not None and camp.status == "SUCCESS"
    if not checks["campaign_ok"]:
        issues.append("campaign not in SUCCESS state")

    # 5. account health + permission
    from app.db.models import PlatformAccount

    acct = session.get(PlatformAccount, job.platform_account_id) if job.platform_account_id else None
    if cap.auto_publish_possible:
        checks["account_connected"] = acct is not None and connection_state(acct) in (CONNECTED, TOKEN_EXPIRING)
        if not checks["account_connected"]:
            issues.append("platform account not connected / token invalid")
    else:
        checks["account_connected"] = True  # manual/not-supported paths don't need a live token

    checks["permission_ok"] = cap.publishing_status not in ("NOT_SUPPORTED",)

    # 6. posting limit (24h)
    cap_24h = _limit(plat, "posts_24h", 1_000_000)
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    published_24h = (session.query(func.count(Publication.id))
                     .filter(Publication.platform == plat, Publication.status == "PUBLISHED",
                             Publication.published_at >= since).scalar() or 0)
    checks["posting_limit_ok"] = published_24h < cap_24h
    if not checks["posting_limit_ok"]:
        issues.append(f"24h posting limit reached for {plat} ({published_24h}/{cap_24h})")

    hard = ["media_readable", "campaign_ok", "account_connected", "permission_ok",
            "title_len_ok", "caption_len_ok", "posting_limit_ok"]
    ok = all(checks.get(k, True) for k in hard)
    return PreflightReport(ok=ok, checks=checks, issues=issues)
