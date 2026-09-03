from __future__ import annotations

import os

from app.agents.media_runner import run_media_pipeline
from app.db.base import session_scope
from app.db.models import Asset, PlatformContent, Scene
from app.platforms import get_platform
from app.providers.media import get_storage


def regenerate_scene(campaign_id: str, scene_id: str, *,
                     visual_prompt: dict | None = None,
                     narration: str | None = None,
                     camera_motion: str | None = None) -> dict:
    """Rebuild ONE scene's assets and re-render — never the whole campaign.

    Existing SUCCESS assets for other scenes are reused (idempotent nodes), so
    only the targeted scene is regenerated before the final render + QA re-run.
    """
    stg = get_storage()
    with session_scope() as session:
        scene = session.get(Scene, scene_id)
        if scene is None or scene.campaign_id != campaign_id:
            raise ValueError("scene not found for campaign")
        content = session.get(PlatformContent, scene.content_id)
        spec = get_platform(content.platform)
        order = scene.scene_order

        if visual_prompt is not None:
            scene.visual_prompt = {**(scene.visual_prompt or {}), **visual_prompt}
            scene.negative_prompt = scene.visual_prompt.get("negative_prompt", scene.negative_prompt)
        if narration is not None:
            scene.narration = narration
        if camera_motion is not None:
            scene.camera_motion = camera_motion
            scene.motion_effect = "manual"
        scene.generation_status = "PENDING"
        scene.asset_id = None

        for a in session.query(Asset).filter(
            Asset.scene_id == scene_id, Asset.asset_type.in_(["image", "audio"])
        ):
            if a.storage_path and os.path.isfile(a.storage_path):
                try:
                    os.remove(a.storage_path)
                except OSError:
                    pass
            session.delete(a)

        platforms = [c.platform for c in
                     session.query(PlatformContent).filter_by(campaign_id=campaign_id)]

    # drop the cached scene clip so the renderer rebuilds it
    clip = stg.campaign_dir(campaign_id, spec.storage_dir, "render", "clips",
                            f"scene_{order:03d}.mp4")
    if os.path.isfile(clip):
        os.remove(clip)

    state = run_media_pipeline(campaign_id, platforms, resume=False)
    return {"campaign_id": campaign_id, "scene_id": scene_id,
            "status": state.get("status"), "media_qa": state.get("media_qa")}
