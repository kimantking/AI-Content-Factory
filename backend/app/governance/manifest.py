"""Rights Manifest (§6, §85, §107, §137) — built from the ASSETS ACTUALLY USED in
the final render, not the plan. Persisted so it survives asset-cache cleanup.
"""
from __future__ import annotations

import hashlib
import os

from sqlalchemy.orm import Session

from app.db.models import Asset, Campaign, PlatformContent
from app.db.models_gov import AssetLineage, RightsLedger, RightsManifest


def _file_hash(path: str) -> str:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def record_lineage(db: Session, *, asset_id: str, operation: str, parent_asset_id: str | None = None,
                   tool: str = "", version: str = "", detail: dict | None = None,
                   workspace_id: str | None = None) -> AssetLineage:
    row = AssetLineage(asset_id=asset_id, parent_asset_id=parent_asset_id, operation=operation,
                       tool=tool, version=version, detail=detail or {}, workspace_id=workspace_id)
    db.add(row)
    db.flush()
    return row


def build_manifest(db: Session, *, campaign_id: str, content_id: str | None = None,
                   publication_id: str | None = None, governance_decision: str = "",
                   published_snapshot: bool = False) -> RightsManifest:
    camp = db.get(Campaign, campaign_id)
    content = db.get(PlatformContent, content_id) if content_id else None

    q = db.query(Asset).filter(Asset.campaign_id == campaign_id)
    if content_id:
        q = q.filter((Asset.content_id == content_id) | (Asset.content_id.is_(None)))
    assets = q.all()
    render = next((a for a in assets if a.asset_type == "render"), None)

    led_by_asset = {r.asset_id: r for r in db.query(RightsLedger)
                    .filter(RightsLedger.campaign_id == campaign_id).all()}

    items = []
    restrictions = []
    attributions = []
    ai_assets = []
    for a in assets:
        if a.asset_type in ("subtitle",):  # code-generated captions: no third-party rights
            continue
        led = led_by_asset.get(a.id)
        entry = {
            "asset_id": a.id, "type": a.asset_type, "provider": a.provider,
            "provider_mode": a.provider_mode, "path": a.storage_path,
            "rights_id": led.id if led else None,
            "rights_status": led.rights_status if led else "UNKNOWN_RIGHTS",
            "source_type": led.source_type if led else "UNKNOWN",
            "license": led.license_type if led else "UNKNOWN",
            "attribution_required": bool(led.attribution_required) if led else False,
            "expiration_at": led.expiration_at.isoformat() if led and led.expiration_at else None,
        }
        items.append(entry)
        if led:
            if led.attribution_required and led.attribution_text:
                attributions.append({"asset_id": a.id, "text": led.attribution_text})
            if led.usage_restrictions:
                restrictions.append({"asset_id": a.id, "restrictions": led.usage_restrictions})
            if led.ai_generated:
                ai_assets.append({"asset_id": a.id, "model": f"{led.model_provider}/{led.model_name}".strip("/")})

    manifest = {
        "video_id": render.id if render else None,
        "campaign_id": campaign_id, "content_id": content_id,
        "brand_id": camp.brand_id if camp else None,
        "channel_id": camp.channel_id if camp else None,
        "platform": content.platform if content else None,
        "assets": items,
        "music": [i for i in items if i["type"] == "music"],
        "sfx": [i for i in items if i["type"] == "sfx"],
        "screenshots": [i for i in items if i["type"] == "screenshot"],
        "charts": [i for i in items if i["type"] == "chart"],
        "ai_generated_assets": ai_assets,
        "attributions": attributions,
        "restrictions": restrictions,
        "unknown_rights_assets": [i["asset_id"] for i in items if i["rights_status"] == "UNKNOWN_RIGHTS"],
        "disclosure_required": bool(ai_assets),
        "governance_result": governance_decision,
    }
    content_hash = _file_hash(render.storage_path) if render and render.storage_path else ""

    row = RightsManifest(
        workspace_id=camp.workspace_id if camp else None,
        brand_id=camp.brand_id if camp else None,
        channel_id=camp.channel_id if camp else None,
        campaign_id=campaign_id, content_id=content_id, publication_id=publication_id,
        render_asset_id=render.id if render else None,
        manifest=manifest, governance_decision=governance_decision,
        content_hash=content_hash, is_published_snapshot=published_snapshot,
    )
    db.add(row)
    db.flush()
    return row
