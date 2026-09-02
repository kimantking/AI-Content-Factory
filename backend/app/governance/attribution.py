"""Attribution engine (§65, §66) — collect assets needing attribution and build a
per-placement package. Attribution does NOT create rights (§66): an asset with no
rights + an attribution line is still BLOCK.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Asset
from app.db.models_gov import RightsLedger


def collect(db: Session, campaign_id: str) -> list[dict]:
    rows = (db.query(RightsLedger).filter_by(campaign_id=campaign_id)
            .filter(RightsLedger.attribution_required.is_(True)).all())
    out = []
    for r in rows:
        a = db.get(Asset, r.asset_id)
        out.append({
            "asset_id": r.asset_id, "type": a.asset_type if a else "?",
            "creator": r.original_creator or r.source_provider or "Unknown",
            "license": r.license_type, "source": r.source_url_or_id or r.source_reference,
            "text": r.attribution_text or _default_line(r),
            "rights_status": r.rights_status,
            "usable": r.rights_status not in ("UNKNOWN_RIGHTS", "EXPIRED", "BLOCKED", "DISPUTED"),
        })
    return out


def _default_line(r: RightsLedger) -> str:
    creator = r.original_creator or r.source_provider or "Unknown"
    lic = r.license_type
    src = r.source_url_or_id or ""
    return f"{creator} — {lic}" + (f" ({src})" if src else "")


def build_attribution_package(db: Session, campaign_id: str) -> dict:
    items = collect(db, campaign_id)
    lines = [i["text"] for i in items if i["usable"]]
    unusable = [i["asset_id"] for i in items if not i["usable"]]
    block = "출처 및 라이선스\n" + "\n".join(f"- {ln}" for ln in lines) if lines else ""
    return {
        "items": items,
        "description_block": block,          # for YouTube/Naver description
        "caption_suffix": (" · " + "; ".join(lines[:2])) if lines else "",  # short platforms
        "credits_section": lines,
        "unusable_assets": unusable,         # attribution can't fix these — still BLOCK
        "note": "attribution does not grant rights; unusable_assets must be replaced",
    }
