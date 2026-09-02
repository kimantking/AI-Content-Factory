"""Governance one-click safe fixes (§103, §104, §136) — reuses the Advanced Video
Studio Smart Rerender so a single bad asset never forces a full re-generate.

Legal ambiguity is never "auto-resolved" (§103): those stay HUMAN_REVIEW /
LEGAL_REVIEW_REQUIRED.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Asset, Scene
from app.db.models_gov import GovernanceEvent, RightsLedger
from app.governance.attribution import build_attribution_package
from app.governance.rights import record_asset_rights

# reason code -> fix strategy (or None = needs a human / legal review)
_STRATEGY = {
    "RIGHTS.UNKNOWN_IN_AUTO": "replace_asset_licensed",
    "RIGHTS.UNKNOWN": "replace_asset_licensed",
    "RIGHTS.PLATFORM_RESTRICTED": "replace_asset_licensed",
    "RIGHTS.WATERMARK": "replace_asset_licensed",
    "RIGHTS.ATTRIBUTION_NEEDED": "add_attribution_package",
    "DISCLOSURE.MISSING": "add_disclosure_meta",
    "DISCLOSURE.PLATFORM_FIELD_MISSING": "set_platform_ai_field",
    "DISCLOSURE.RECOMMENDED": "add_disclosure_meta",
    "ORIGINALITY.HIGH_SIMILARITY": None,
    "ORIGINALITY.DUPLICATE": None,
    "CLAIM.UNSUPPORTED": None,
    "CLAIM.CHART_MISMATCH": None,
    "VOICE.CLONE_NO_CONSENT": None,
    "ENDORSEMENT.PUBLIC_FIGURE": None,
    "PRIVACY.HIGH_RISK_PII": None,
    "TRADEMARK.BLOCK": None,
    "POLICY.STALE": "refresh_policy",
}


def plan_fixes(governance_result: dict) -> list[dict]:
    out: list[dict] = []
    for code in governance_result.get("reason_codes", []):
        strat = _STRATEGY.get(code, "MANUAL_REVIEW")
        out.append({"reason_code": code, "strategy": strat,
                    "auto_fixable": strat not in (None, "MANUAL_REVIEW")})
    # de-dup by strategy
    seen = set()
    dedup = []
    for f in out:
        key = f["strategy"] or f["reason_code"]
        if key in seen:
            continue
        seen.add(key)
        dedup.append(f)
    return dedup


def apply_fix(db: Session, *, campaign_id: str, content_id: str | None, reason_code: str,
              workspace_id: str | None = None) -> dict:
    strat = _STRATEGY.get(reason_code)
    if strat in (None, "MANUAL_REVIEW"):
        return {"applied": False, "reason": "requires human / legal review — not auto-fixable"}

    if strat == "replace_asset_licensed":
        # swap every UNKNOWN_RIGHTS / watermarked image asset for a licensed mock stock still
        led_rows = (db.query(RightsLedger).filter_by(campaign_id=campaign_id)
                    .filter(RightsLedger.rights_status.in_(["UNKNOWN_RIGHTS", "BLOCKED", "EXPIRED"])).all())
        replaced = []
        for led in led_rows:
            asset = db.get(Asset, led.asset_id)
            if asset is None or asset.asset_type not in ("image", "music", "sfx"):
                continue
            # mark a licensed replacement in the ledger (the actual re-render happens
            # via Smart Rerender on the affected scene only)
            new_led = record_asset_rights(
                db, asset_id=led.asset_id, source_type="STOCK_LICENSED",
                workspace_id=workspace_id or led.workspace_id, brand_id=led.brand_id,
                channel_id=led.channel_id, campaign_id=campaign_id,
                source_provider="mock_stock", license_type="COMMERCIAL_STOCK",
                license_reference="mock-license-auto-fix", evidence_ids=led.evidence_ids,
                notes="auto-fix: replaced unknown-rights asset with a licensed mock stock item")
            led.rights_status = "RESTRICTED"   # supersede the old row
            led.notes = (led.notes + " [superseded by auto-fix]").strip()
            replaced.append({"asset_id": led.asset_id, "new_rights_id": new_led.id})
        db.add(GovernanceEvent(campaign_id=campaign_id, content_id=content_id, kind="ASSET_REPLACED",
                               detail={"reason_code": reason_code, "replaced": replaced}))
        db.flush()
        return {"applied": True, "strategy": strat, "replaced": replaced,
                "note": "affected scenes require Smart Rerender + governance recheck"}

    if strat == "add_attribution_package":
        pkg = build_attribution_package(db, campaign_id=campaign_id)
        db.add(GovernanceEvent(campaign_id=campaign_id, content_id=content_id, kind="DISCLOSURE_ADDED",
                               detail={"reason_code": reason_code, "attribution": pkg}))
        db.flush()
        return {"applied": True, "strategy": strat, "attribution_package": pkg}

    if strat in ("add_disclosure_meta", "set_platform_ai_field"):
        from app.db.models import PlatformContent
        content = db.get(PlatformContent, content_id) if content_id else \
            db.query(PlatformContent).filter_by(campaign_id=campaign_id).first()
        if content is not None:
            meta = dict((content.payload or {}).get("disclosure_meta", {}))
            meta["disclosure_required"] = True
            if strat == "set_platform_ai_field":
                meta["platform_ai_field"] = True
            meta.setdefault("disclosure_text", "이 콘텐츠에는 AI가 생성/합성한 요소가 포함되어 있습니다.")
            content.payload = {**(content.payload or {}), "disclosure_meta": meta}
            db.add(GovernanceEvent(campaign_id=campaign_id, content_id=content.id, kind="DISCLOSURE_ADDED",
                                   detail={"reason_code": reason_code, "meta": meta}))
            db.flush()
        return {"applied": True, "strategy": strat}

    if strat == "refresh_policy":
        from app.governance.policy import seed_policy_registry
        n = seed_policy_registry(db, force=True)
        return {"applied": True, "strategy": strat, "rules_refreshed": n}

    return {"applied": False, "reason": f"unknown strategy {strat}"}
