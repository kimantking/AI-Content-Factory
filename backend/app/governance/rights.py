"""Rights Ledger + rights-status resolution (§2, §3, §63, §64).

Every media asset gets a RightsLedger row. `rights_status` is derived from
source_type + license + provenance + consent + expiration — never assumed
permissive. Unknown ⇒ `UNKNOWN_RIGHTS` and blocked from FULL_AUTO publishing.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models_gov import RightsEvidence, RightsLedger
from app.governance.licenses import commercial_ok, interpret

# source_type -> default license key + default status when nothing else is known
_SOURCE_DEFAULTS = {
    "AI_GENERATED": ("MODEL_OUTPUT_COMMERCIAL", "AI_GENERATED_VERIFIED"),
    "GENERATED_IMAGE": ("MODEL_OUTPUT_COMMERCIAL", "AI_GENERATED_VERIFIED"),
    "GENERATED_VIDEO": ("MODEL_OUTPUT_COMMERCIAL", "AI_GENERATED_VERIFIED"),
    "GENERATED_AUDIO": ("MODEL_OUTPUT_COMMERCIAL", "AI_GENERATED_VERIFIED"),
    "PUBLIC_DOMAIN": ("PUBLIC_DOMAIN", "PUBLIC_DOMAIN_VERIFIED"),
    "STOCK_LICENSED": ("COMMERCIAL_STOCK", "LICENSED"),
    "MUSIC_LIBRARY": ("PROVIDER_MUSIC", "LICENSED"),
    "SFX_LIBRARY": ("PROVIDER_MUSIC", "LICENSED"),
    "INTERNAL_ASSET": ("USER_OWNED", "USER_OWNED"),
    "USER_UPLOAD": ("UNKNOWN", "UNKNOWN_RIGHTS"),
    "SCREENSHOT": ("UNKNOWN", "UNKNOWN_RIGHTS"),
    "SOCIAL_POST": ("UNKNOWN", "UNKNOWN_RIGHTS"),
    "NEWS_MEDIA": ("UNKNOWN", "UNKNOWN_RIGHTS"),
    "OFFICIAL_SOURCE": ("UNKNOWN", "UNKNOWN_RIGHTS"),
    "UNKNOWN": ("UNKNOWN", "UNKNOWN_RIGHTS"),
}

# rights statuses that are safe for unattended (FULL_AUTO) publishing
AUTO_SAFE_STATUS = {
    "VERIFIED", "LICENSED", "USER_OWNED", "AI_GENERATED_VERIFIED", "PUBLIC_DOMAIN_VERIFIED",
}
# VERIFIED_WITH_ATTRIBUTION is auto-safe only once the attribution package exists


def resolve_status(db: Session, led: RightsLedger) -> str:
    """Deterministic status from the ledger row's fields."""
    now = datetime.now(timezone.utc)

    if led.rights_status == "BLOCKED":
        return "BLOCKED"
    if led.watermark_detected:
        return "BLOCKED"                       # third-party watermark (§43)
    if led.voice_kind == "CLONED_VOICE" and led.consent_status not in ("USER_CONFIRMED", "DOCUMENTED"):
        return "BLOCKED"                       # voice clone w/o consent (§37)
    if led.person_status == "SYNTHETIC_PERSON" and led.trademark_flag == "MISLEADING_ASSOCIATION_RISK":
        return "DISPUTED"

    exp = led.expiration_at
    if exp is not None:
        exp = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
        if exp < now:
            return "EXPIRED"

    lic = interpret(db, led.license_type)
    comm = commercial_ok(db, led.license_type)

    if led.source_type in ("AI_GENERATED", "GENERATED_IMAGE", "GENERATED_VIDEO", "GENERATED_AUDIO"):
        if led.model_terms_reference or led.model_provider:
            return "AI_GENERATED_VERIFIED" if comm != "NO" else "RESTRICTED"
        return "UNKNOWN_RIGHTS"

    if led.source_type == "PUBLIC_DOMAIN" and lic["key"] in ("PUBLIC_DOMAIN", "CC0"):
        return "PUBLIC_DOMAIN_VERIFIED"

    if led.source_type == "USER_UPLOAD":
        if led.consent_status == "REVOKED":
            return "RESTRICTED"
        if led.user_supplied and led.rights_status == "USER_OWNED":
            return "USER_OWNED"
        return "UNKNOWN_RIGHTS"

    if led.source_type in ("STOCK_LICENSED", "MUSIC_LIBRARY", "SFX_LIBRARY"):
        if comm == "NO":
            return "RESTRICTED"
        if not led.license_reference and not led.evidence_ids:
            return "UNKNOWN_RIGHTS"            # claimed licensed but no proof
        return "VERIFIED_WITH_ATTRIBUTION" if led.attribution_required else "LICENSED"

    if led.source_type in ("SCREENSHOT", "SOCIAL_POST", "NEWS_MEDIA", "OFFICIAL_SOURCE"):
        # referencing a fact ≠ a right to reproduce the media (§58)
        return "UNKNOWN_RIGHTS"

    if comm == "YES" and lic["known"]:
        return "VERIFIED_WITH_ATTRIBUTION" if lic["attribution_required"] else "VERIFIED"
    return "UNKNOWN_RIGHTS"


def record_asset_rights(db: Session, *, asset_id: str, source_type: str,
                        workspace_id: str | None = None, brand_id: str | None = None,
                        channel_id: str | None = None, campaign_id: str | None = None,
                        source_provider: str = "", source_url_or_id: str = "",
                        license_type: str | None = None, license_reference: str = "",
                        attribution_required: bool | None = None, attribution_text: str = "",
                        expiration_at: datetime | None = None,
                        ai_generated: bool = False, model_provider: str = "", model_name: str = "",
                        model_terms_reference: str = "", user_supplied: bool = False,
                        consent_status: str = "", voice_kind: str = "", person_status: str = "",
                        watermark_detected: bool = False, platform_restrictions: dict | None = None,
                        content_id_risk: bool = False, evidence_ids: list | None = None,
                        cost_usd: float = 0.0, notes: str = "") -> RightsLedger:
    default_lic, _default_status = _SOURCE_DEFAULTS.get(source_type, ("UNKNOWN", "UNKNOWN_RIGHTS"))
    lic_key = (license_type or default_lic).upper().replace(" ", "_")
    lic = interpret(db, lic_key)
    attr_req = lic["attribution_required"] if attribution_required is None else attribution_required

    row = RightsLedger(
        workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id,
        asset_id=asset_id, campaign_id=campaign_id, source_type=source_type,
        source_provider=source_provider, source_url_or_id=source_url_or_id,
        license_type=lic_key, license_reference=license_reference,
        commercial_use=commercial_ok(db, lic_key),
        derivative_use=lic["derivative_allowed"], redistribution_allowed="UNKNOWN",
        attribution_required=attr_req, attribution_text=attribution_text,
        expiration_at=expiration_at,
        platform_restrictions=platform_restrictions or {},
        ai_generated=ai_generated or source_type.startswith("GENERATED") or source_type == "AI_GENERATED",
        model_generated=ai_generated, model_provider=model_provider, model_name=model_name,
        model_terms_reference=model_terms_reference, user_supplied=user_supplied,
        human_generated=(source_type in ("USER_UPLOAD", "INTERNAL_ASSET") and not ai_generated),
        consent_status=consent_status, voice_kind=voice_kind, person_status=person_status,
        watermark_detected=watermark_detected, content_id_risk=content_id_risk,
        evidence_ids=evidence_ids or [], cost_usd=cost_usd, notes=notes,
        rights_status="UNKNOWN_RIGHTS",
    )
    db.add(row)
    db.flush()
    row.rights_status = resolve_status(db, row)
    db.flush()
    return row


def add_evidence(db: Session, *, rights_id: str, type: str, provider: str = "",
                 reference: str = "", summary: str = "", content_hash: str = "",
                 workspace_id: str | None = None) -> RightsEvidence:
    ev = RightsEvidence(rights_id=rights_id, type=type, provider=provider, reference=reference,
                        summary=summary[:2000], content_hash=content_hash, workspace_id=workspace_id)
    db.add(ev)
    db.flush()
    led = db.get(RightsLedger, rights_id)
    if led is not None:
        led.evidence_ids = list(led.evidence_ids or []) + [ev.id]
        led.rights_status = resolve_status(db, led)
        db.flush()
    return ev


def platform_allows(led: RightsLedger, platform: str) -> bool:
    """Music/asset platform restrictions (§60) — default allow unless explicitly denied."""
    pr = led.platform_restrictions or {}
    if platform in pr:
        return bool(pr[platform])
    # 'allowed' allowlist form
    if "allowed" in pr and isinstance(pr["allowed"], list):
        return platform in pr["allowed"]
    if "denied" in pr and isinstance(pr["denied"], list):
        return platform not in pr["denied"]
    return True
