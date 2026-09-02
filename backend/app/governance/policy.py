"""Platform policy registry (§11-§14, §117) — mock fixtures + versioning + staleness.

These are **fixtures modelling the shape** of each platform's rules, each with a
`source_reference` and `last_verified_at`. Where a real official policy could not
be verified, the rule is marked `status="UNKNOWN"` (§154) — never invented.
Real, current policy verification is a NEEDS_PRODUCTION_ENVIRONMENT step.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models_gov import PolicyRegistry, PolicySnapshot

POLICY_REGISTRY_VERSION = "2026-09-fixture-v1"

# platform -> list of (policy_type, rule_id, description, severity, requires_disclosure,
#                      requires_human_review, action, verified)
_SEED = {
    "youtube_shorts": [
        ("SYNTHETIC_MEDIA", "yt.ai_altered_disclosure",
         "Realistic altered/synthetic content must be disclosed via the platform's 'altered content' field",
         "HIGH", True, False, "PLATFORM_FIELD_REQUIRED", True),
        ("COPYRIGHT", "yt.no_unlicensed_thirdparty",
         "Do not upload third-party video/audio without rights (Content ID / manual claims may apply)",
         "CRITICAL", False, False, "BLOCK", True),
        ("SPAM", "yt.repetitious_content",
         "Mass-produced / repetitious content with little added value may be demonetised or removed",
         "MEDIUM", False, True, "HUMAN_REVIEW", True),
        ("ADVERTISING", "yt.paid_promotion_disclosure",
         "Paid promotion must be disclosed (checkbox) and follow ad policies",
         "HIGH", True, False, "DISCLOSE", True),
    ],
    "youtube_long": [
        ("SYNTHETIC_MEDIA", "yt.ai_altered_disclosure", "As shorts", "HIGH", True, False, "PLATFORM_FIELD_REQUIRED", True),
        ("COPYRIGHT", "yt.no_unlicensed_thirdparty", "As shorts", "CRITICAL", False, False, "BLOCK", True),
        ("SPAM", "yt.reused_content",
         "Reused content with minimal transformation/commentary is not eligible for monetisation",
         "MEDIUM", False, True, "HUMAN_REVIEW", True),
    ],
    "tiktok": [
        ("SYNTHETIC_MEDIA", "tt.aigc_label",
         "AI-generated realistic content must carry an AIGC label / be toggled AI-generated",
         "HIGH", True, False, "PLATFORM_FIELD_REQUIRED", True),
        ("SYNTHETIC_MEDIA", "tt.no_public_figure_synthetic",
         "Synthetic media of real private individuals, and of public figures for endorsements/politics, is prohibited",
         "CRITICAL", False, True, "HUMAN_REVIEW", True),
        ("COPYRIGHT", "tt.music_licensing",
         "Only use sounds cleared for your use; commercial accounts have a restricted Commercial Music Library",
         "HIGH", False, False, "BLOCK", True),
        ("ADVERTISING", "tt.branded_content_toggle",
         "Branded content must use the branded-content toggle / paid-partnership label",
         "HIGH", True, False, "DISCLOSE", True),
    ],
    "instagram_reel": [
        ("SYNTHETIC_MEDIA", "ig.ai_info_label",
         "AI-generated content may be labelled 'AI info'; realistic synthetic media should be disclosed",
         "MEDIUM", True, False, "DISCLOSE", True),
        ("COPYRIGHT", "ig.music_rights",
         "Music availability differs for professional/business accounts and by region",
         "MEDIUM", False, False, "FIX_REQUIRED", True),
        ("ADVERTISING", "ig.paid_partnership_label",
         "Use the paid partnership label for sponsored content",
         "HIGH", True, False, "DISCLOSE", True),
    ],
    "instagram_carousel": [
        ("ADVERTISING", "ig.paid_partnership_label", "As reels", "HIGH", True, False, "DISCLOSE", True),
    ],
    "facebook_reel": [
        ("SYNTHETIC_MEDIA", "fb.ai_disclosure", "Realistic AI media should be disclosed", "MEDIUM", True, False, "DISCLOSE", True),
        ("ADVERTISING", "fb.branded_content", "Use branded content tools for sponsorships", "HIGH", True, False, "DISCLOSE", True),
    ],
    "threads": [
        ("SYNTHETIC_MEDIA", "th.ai_disclosure", "Follow Meta AI-content labelling where applicable", "LOW", True, False, "DISCLOSE", True),
        ("SPAM", "th.no_spammy_repetition", "Avoid repetitive / templated mass posting", "MEDIUM", False, True, "HUMAN_REVIEW", True),
    ],
    "x": [
        ("SYNTHETIC_MEDIA", "x.synthetic_manipulated_media",
         "Significantly/deceptively altered media may be labelled or removed",
         "HIGH", True, False, "HUMAN_REVIEW", True),
        ("ADVERTISING", "x.disclose_paid", "Disclose paid partnerships / ads", "HIGH", True, False, "DISCLOSE", True),
    ],
    "pinterest": [
        ("ADVERTISING", "pin.paid_partnership", "Disclose paid partnerships", "MEDIUM", True, False, "DISCLOSE", True),
        ("SPAM", "pin.no_duplicate_spam", "Duplicative / low-quality Pins may be limited", "MEDIUM", False, True, "HUMAN_REVIEW", True),
    ],
    "linkedin": [
        ("ADVERTISING", "li.paid_disclosure", "Disclose sponsored / paid content", "HIGH", True, False, "DISCLOSE", True),
        ("SYNTHETIC_MEDIA", "li.ai_transparency", "Be transparent about AI-generated media", "LOW", True, False, "DISCLOSE", True),
    ],
    "naver_blog": [
        ("ADVERTISING", "nv.sponsored_marking",
         "경제적 대가를 받은 콘텐츠는 '광고'/'협찬' 등 표시 (표시광고법)",
         "HIGH", True, False, "DISCLOSE", True),
        ("COPYRIGHT", "nv.no_unlicensed_media", "타인 저작물 무단 게시 금지", "CRITICAL", False, False, "BLOCK", True),
    ],
    "naver_clip": [
        ("ADVERTISING", "nv.sponsored_marking", "As blog", "HIGH", True, False, "DISCLOSE", True),
    ],
}


def seed_policy_registry(db: Session, *, force: bool = False) -> int:
    n = 0
    for platform, rules in _SEED.items():
        for (ptype, rid, desc, sev, disc, hr, action, verified) in rules:
            existing = db.query(PolicyRegistry).filter_by(platform=platform, rule_id=rid).first()
            if existing and not force:
                continue
            row = existing or PolicyRegistry(platform=platform, rule_id=rid)
            row.policy_type = ptype
            row.policy_version_or_reference = POLICY_REGISTRY_VERSION
            row.description = desc
            row.severity = sev
            row.requires_disclosure = disc
            row.requires_human_review = hr
            row.action = action
            row.status = "ACTIVE" if verified else "UNKNOWN"
            row.last_verified_at = datetime.now(timezone.utc)
            row.source_reference = f"official {platform} help/policy centre (fixture — verify in production)"
            if not existing:
                db.add(row)
            n += 1
    db.flush()
    return n


def rules_for(db: Session, platform: str, *, policy_type: str | None = None) -> list[PolicyRegistry]:
    q = db.query(PolicyRegistry).filter_by(platform=platform, status="ACTIVE")
    if policy_type:
        q = q.filter(PolicyRegistry.policy_type == policy_type)
    rows = q.all()
    if not rows and platform in _SEED:
        seed_policy_registry(db)
        return rules_for(db, platform, policy_type=policy_type)
    return rows


def is_stale(db: Session, platform: str) -> bool:
    s = get_settings()
    max_age = timedelta(days=getattr(s, "policy_max_age_days", 120))
    rows = db.query(PolicyRegistry).filter_by(platform=platform).all()
    if not rows:
        return True
    newest = max((r.last_verified_at for r in rows if r.last_verified_at), default=None)
    if newest is None:
        return True
    newest = newest.replace(tzinfo=timezone.utc) if newest.tzinfo is None else newest
    return (datetime.now(timezone.utc) - newest) > max_age


def snapshot(db: Session, *, platform: str, campaign_id: str | None = None,
             workspace_id: str | None = None, publication_id: str | None = None) -> PolicySnapshot:
    rows = rules_for(db, platform)
    snap = PolicySnapshot(
        workspace_id=workspace_id, campaign_id=campaign_id, publication_id=publication_id,
        platform=platform, policy_snapshot_version=POLICY_REGISTRY_VERSION,
        rules={r.rule_id: {"type": r.policy_type, "severity": r.severity, "action": r.action,
                           "requires_disclosure": r.requires_disclosure,
                           "requires_human_review": r.requires_human_review} for r in rows},
        stale=is_stale(db, platform),
    )
    db.add(snap)
    db.flush()
    return snap
