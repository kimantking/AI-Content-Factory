from __future__ import annotations

import os

from app.db.models import Asset
from app.media.ffmpeg import probe, run_ffmpeg
from app.platforms import get_platform
from app.providers.media import get_storage


def needs_normalize(asset: Asset, platform: str) -> tuple[bool, str]:
    if not asset.storage_path.endswith((".mp4", ".mov")):
        return False, ""
    try:
        pspec = get_platform(platform)
    except KeyError:
        return False, ""
    ew, eh = pspec.resolution()
    info = probe(asset.storage_path)
    w, h = info.get("width"), info.get("height")
    if not w or not h:
        return False, ""
    if (w, h) != (ew, eh):
        return True, f"resolution {w}x{h} -> {ew}x{eh}"
    return False, ""


def normalize_asset(session, asset: Asset, platform: str) -> Asset | None:
    """Re-encode to the platform spec into a NEW asset. The original is never
    overwritten. Returns the normalized Asset, or None if no change needed."""
    do, reason = needs_normalize(asset, platform)
    if not do:
        return None
    pspec = get_platform(platform)
    ew, eh = pspec.resolution()
    stg = get_storage()
    out_dir = stg.campaign_dir(asset.campaign_id, pspec.storage_dir, "normalized")
    out = os.path.join(out_dir, f"{platform}_{os.path.basename(asset.storage_path)}")
    run_ffmpeg([
        "-i", asset.storage_path,
        "-vf", f"scale={ew}:{eh}:force_original_aspect_ratio=decrease,"
               f"pad={ew}:{eh}:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out,
    ])
    row = Asset(
        campaign_id=asset.campaign_id, content_id=asset.content_id, scene_id=None,
        asset_type=asset.asset_type, provider="ffmpeg-normalizer", provider_mode="REAL",
        prompt="", hash="", storage_path=out, mime_type="video/mp4",
        width=ew, height=eh, duration=asset.duration, cost=0.0,
        meta={"normalized_from": asset.id, "reason": reason, "platform": platform},
        status="SUCCESS",
    )
    session.add(row)
    session.flush()
    return row
