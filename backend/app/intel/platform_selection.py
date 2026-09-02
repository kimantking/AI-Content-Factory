"""SNS Platform Selection — three-state selection per platform/content-type, the
generation-skip router, the publisher final gate, and cost preview.

DISABLED             — nothing generated, nothing published, no API calls.
GENERATE_ONLY        — content + media generated; NO PublishJob.
GENERATE_AND_PUBLISH — generated + a PublishJob is created.

A platform the user explicitly turned off is a HARD campaign rule
(USER_EXPLICIT_SELECTION) — Autopilot cannot turn it back on.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Campaign
from app.db.models_learn import CampaignPlatformSelection, PlatformPreset

# spec §AQ — platform -> its content types (first entry is the default)
CONTENT_TYPES: dict[str, list[str]] = {
    "youtube_shorts": ["SHORT_VIDEO"],
    "youtube_long": ["LONG_VIDEO"],
    "tiktok": ["VIDEO"],
    "instagram_reel": ["REELS"],
    "instagram_feed": ["FEED"],
    "instagram_carousel": ["CAROUSEL"],
    "facebook_reel": ["REELS"],
    "threads": ["TEXT", "THREAD", "IMAGE", "VIDEO"],
    "x": ["POST", "THREAD", "IMAGE", "VIDEO"],
    "pinterest": ["IMAGE_PIN", "VIDEO_PIN"],
    "linkedin": ["TEXT", "IMAGE", "VIDEO", "DOCUMENT"],
    "naver_blog": ["ARTICLE"],
    "naver_clip": ["CLIP"],
}

ALL_PLATFORMS = list(CONTENT_TYPES)

MODES = ("DISABLED", "GENERATE_ONLY", "GENERATE_AND_PUBLISH")

# builtin presets (spec §AV)
BUILTIN_PRESETS: dict[str, dict] = {
    "shortform_all": {p: {ct: "GENERATE_AND_PUBLISH" for ct in CONTENT_TYPES[p]}
                      for p in ("youtube_shorts", "tiktok", "instagram_reel",
                                "facebook_reel", "naver_clip")},
    "text_all": {p: {ct: "GENERATE_AND_PUBLISH" for ct in CONTENT_TYPES[p]}
                 for p in ("threads", "x", "linkedin", "naver_blog")},
    "youtube_only": {"youtube_shorts": {"SHORT_VIDEO": "GENERATE_AND_PUBLISH"},
                     "youtube_long": {"LONG_VIDEO": "GENERATE_ONLY"}},
}


def _mode(v) -> str:
    v = str(v or "").upper()
    return v if v in MODES else "DISABLED"


def normalize_selection(selection: dict) -> dict:
    """{platform: {content_type: mode}} | {platform: mode} -> canonical form."""
    out: dict[str, dict[str, str]] = {}
    for p, val in (selection or {}).items():
        if p not in CONTENT_TYPES:
            continue
        if isinstance(val, str):
            out[p] = {CONTENT_TYPES[p][0]: _mode(val)}
        elif isinstance(val, dict):
            cts = {ct: _mode(m) for ct, m in val.items() if ct in CONTENT_TYPES[p]}
            out[p] = cts or {CONTENT_TYPES[p][0]: "DISABLED"}
    return out


def apply_preset(name: str, db: Session | None = None, *, workspace_id: str | None = None) -> dict:
    if name in BUILTIN_PRESETS:
        return normalize_selection(BUILTIN_PRESETS[name])
    if db is not None:
        row = db.query(PlatformPreset).filter_by(name=name).first()
        if row:
            return normalize_selection(row.selection)
    return {}


# --------------------------------------------------------------------- #
#  persistence + resolution
# --------------------------------------------------------------------- #

def set_selection(db: Session, *, campaign_id: str, selection: dict,
                  workspace_id: str | None = None, brand_id: str | None = None,
                  channel_id: str | None = None, source: str = "USER",
                  user_explicit: bool = True) -> dict:
    canon = normalize_selection(selection)
    db.flush()   # ensure a just-added campaign is persistent before get()/bulk-delete
    db.query(CampaignPlatformSelection).filter_by(campaign_id=campaign_id).delete()
    generate: list[str] = []
    for p, cts in canon.items():
        p_any = False
        for ct, m in cts.items():
            db.add(CampaignPlatformSelection(
                workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id,
                campaign_id=campaign_id, platform=p, content_type=ct, mode=m,
                user_explicit=user_explicit, source=source))
            if m != "DISABLED":
                p_any = True
        if p_any:
            generate.append(p)
    camp = db.get(Campaign, campaign_id)
    if camp is not None:
        camp.platforms = generate                      # pipeline only builds these
        camp.platform_selection_locked = bool(user_explicit)
    db.flush()
    return {"campaign_id": campaign_id, "generate_platforms": generate,
            "publish_platforms": [p for p in generate if _platform_has_publish(canon[p])]}


def _platform_has_publish(cts: dict) -> bool:
    return any(m == "GENERATE_AND_PUBLISH" for m in cts.values())


def resolve_selection(db: Session, campaign_id: str) -> dict:
    """Canonical selection for a campaign. Falls back to Campaign.platforms
    (legacy / autopilot) as GENERATE_AND_PUBLISH when no explicit rows exist."""
    rows = db.query(CampaignPlatformSelection).filter_by(campaign_id=campaign_id).all()
    if rows:
        out: dict[str, dict[str, str]] = {}
        for r in rows:
            out.setdefault(r.platform, {})[r.content_type or CONTENT_TYPES.get(r.platform, ["_"])[0]] = r.mode
        return out
    camp = db.get(Campaign, campaign_id)
    plats = (camp.platforms if camp else []) or []
    return {p: {CONTENT_TYPES.get(p, ["_"])[0]: "GENERATE_AND_PUBLISH"} for p in plats if p in CONTENT_TYPES}


def platforms_to_generate(db: Session, campaign_id: str) -> set[str]:
    sel = resolve_selection(db, campaign_id)
    return {p for p, cts in sel.items() if any(m != "DISABLED" for m in cts.values())}


def platforms_to_publish(db: Session, campaign_id: str) -> set[str]:
    sel = resolve_selection(db, campaign_id)
    return {p for p, cts in sel.items() if any(m == "GENERATE_AND_PUBLISH" for m in cts.values())}


# pipeline content-platform aliases -> selection key
_PLATFORM_ALIAS = {
    "pinterest_image": "pinterest", "pinterest_video": "pinterest",
    "youtube": "youtube_shorts", "instagram": "instagram_reel", "facebook": "facebook_reel",
}


def _sel_key(platform: str, selection: dict) -> str:
    if platform in selection:
        return platform
    a = _PLATFORM_ALIAS.get(platform)
    if a and a in selection:
        return a
    # prefix match (e.g. a future "youtube_live")
    for k in selection:
        if platform.startswith(k.split("_")[0]) and k in selection:
            return k
    return platform


def mode_for(db: Session, campaign_id: str, platform: str, content_type: str | None = None) -> str:
    full = resolve_selection(db, campaign_id)
    sel = full.get(_sel_key(platform, full), {})
    if not sel:
        return "DISABLED"
    if content_type and content_type in sel:
        return sel[content_type]
    # any GENERATE_AND_PUBLISH wins for the platform-level view
    if "GENERATE_AND_PUBLISH" in sel.values():
        return "GENERATE_AND_PUBLISH"
    if "GENERATE_ONLY" in sel.values():
        return "GENERATE_ONLY"
    return "DISABLED"


# --------------------------------------------------------------------- #
#  gates
# --------------------------------------------------------------------- #

def has_explicit_selection(db: Session, campaign_id: str) -> bool:
    return db.query(CampaignPlatformSelection.id).filter_by(campaign_id=campaign_id).first() is not None


def publish_allowed(db: Session, *, campaign_id: str, platform: str,
                    content_type: str | None = None) -> tuple[bool, str]:
    """PlatformSelectionGate — re-read at job creation AND right before the API
    call (covers the queued-job race, spec §AY). Only enforces on campaigns that
    actually used the 3-state selection; legacy / Autopilot campaigns with no
    explicit rows are unaffected."""
    if not has_explicit_selection(db, campaign_id):
        return True, "NO_SELECTION"
    m = mode_for(db, campaign_id, platform, content_type)
    if m == "GENERATE_AND_PUBLISH":
        return True, "GENERATE_AND_PUBLISH"
    return False, m or "DISABLED"


def autopilot_may_enable(db: Session, *, campaign_id: str, platform: str) -> bool:
    """USER_EXPLICIT_SELECTION is a hard campaign rule (spec §AT). If the user
    explicitly turned a platform off, Autopilot cannot turn it on."""
    camp = db.get(Campaign, campaign_id)
    if camp is not None and camp.platform_selection_locked:
        rows = db.query(CampaignPlatformSelection).filter_by(
            campaign_id=campaign_id, platform=platform).all()
        if rows and all(r.user_explicit and r.mode == "DISABLED" for r in rows):
            return False
        if not rows:            # locked campaign, platform not selected -> stays off
            return False
    return True


# --------------------------------------------------------------------- #
#  cost preview (spec §BB — honest; no fabricated $)
# --------------------------------------------------------------------- #

_MEDIA_PLATFORMS = {"youtube_shorts", "youtube_long", "tiktok", "instagram_reel",
                    "instagram_feed", "instagram_carousel", "facebook_reel", "naver_clip"}


def cost_preview(db: Session, *, campaign_id: str, selection: dict | None = None) -> dict:
    from app.config import get_settings

    s = get_settings()
    sel = normalize_selection(selection) if selection else resolve_selection(db, campaign_id)
    media_known = not s.media_provider_is_mock("video")
    per_platform: dict[str, dict] = {}
    total_pieces = total_variants = total_publish = 0
    for p, cts in sel.items():
        gen = [ct for ct, m in cts.items() if m != "DISABLED"]
        pub = [ct for ct, m in cts.items() if m == "GENERATE_AND_PUBLISH"]
        needs_media = p in _MEDIA_PLATFORMS and bool(gen)
        per_platform[p] = {
            "content_pieces": len(gen),
            "media_variants": (1 if needs_media else 0),
            "publish_jobs": len(pub),
            "est_usd": ("PRICING_UNKNOWN" if (needs_media and not media_known) else 0.0),
        }
        total_pieces += len(gen)
        total_variants += per_platform[p]["media_variants"]
        total_publish += len(pub)
    any_unknown = any(v["est_usd"] == "PRICING_UNKNOWN" for v in per_platform.values())
    return {
        "campaign_id": campaign_id,
        "platforms": per_platform,
        "totals": {"content_pieces": total_pieces, "media_variants": total_variants,
                   "publish_jobs": total_publish},
        "total_est_usd": ("PRICING_UNKNOWN" if any_unknown else 0.0),
        "note": ("media providers are MOCK — dollar cost is PRICING_UNKNOWN; the "
                 "structural estimate (pieces / variants / jobs) is exact"),
    }
