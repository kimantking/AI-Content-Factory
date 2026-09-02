"""Load a campaign's persisted scenes into the plain-dict shape the NL-edit +
Smart-Rerender planner expect (AUDIT-P8-002)."""
from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.db.models import Scene


def load_scene_state(db: Session, campaign_id: str) -> tuple[list[dict], dict]:
    rows = (db.query(Scene).filter_by(campaign_id=campaign_id)
            .order_by(Scene.scene_order.asc()).all())
    scenes: list[dict] = []
    sub_parts: list[str] = []
    for s in rows:
        scenes.append({
            "scene_order": int(s.scene_order),
            "still_asset_id": s.asset_id,
            "voice_asset_id": None,
            "camera_motion": s.camera_motion,
            "cinematic_motion": s.motion_effect,
            "estimated_duration": float(s.estimated_duration or 0.0),
            "narration": s.narration or "",
        })
        sub_parts.append(s.subtitle_text or "")
    meta = {
        "subtitle_blocks_hash": hashlib.sha256("\n".join(sub_parts).encode()).hexdigest()[:16],
        "music_style": (rows[0].music_energy if rows else "mid"),
        "total_duration": round(sum(float(r.estimated_duration or 0.0) for r in rows), 1),
    }
    return scenes, meta
