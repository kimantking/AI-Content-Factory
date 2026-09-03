from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import get_db
from app.db.models import Asset, Campaign, CostLog, PlatformContent, Scene
from app.platforms import PLATFORMS

router = APIRouter(prefix="/api", tags=["media"])

MEDIA_STEPS = [
    "media:load_inputs", "media:platform_adapt", "media:scene_plan", "media:visual_direct",
    "media:images", "media:voice", "media:subtitles", "media:edit_decision",
    "media:render", "media:thumbnail", "media:platform_images", "media:qa", "media:done",
]
_ORDER = {s: i for i, s in enumerate(MEDIA_STEPS)}


class StartMediaRequest(BaseModel):
    platforms: list[str] | None = None


class RegenerateRequest(BaseModel):
    narration: str | None = None
    camera_motion: str | None = None
    visual_prompt: dict | None = None


def _rel(path: str) -> str | None:
    if not path or not os.path.isfile(path):
        return None
    root = os.getcwd()
    try:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        return None
    if rel.startswith(("storage/", "outputs/")):
        return "/files/" + rel
    return None


@router.post("/campaigns/{campaign_id}/media", status_code=202)
def start_media(campaign_id: str, payload: StartMediaRequest, db: Session = Depends(get_db)):
    camp = db.get(Campaign, campaign_id)
    if camp is None:
        raise HTTPException(404, "campaign not found")
    if camp.status != "SUCCESS":
        raise HTTPException(409, f"Phase 1-A not complete (status={camp.status})")
    platforms = payload.platforms or camp.platforms or ["youtube_shorts"]
    s = get_settings()
    from app.celery_app import celery_app  # noqa: F401
    from app.tasks import run_media_task

    if s.run_inline:
        run_media_task.apply(args=[campaign_id, platforms])
    else:
        try:
            run_media_task.apply_async(args=[campaign_id, platforms], queue="render")
        except Exception:
            run_media_task.apply(args=[campaign_id, platforms])
    return {"campaign_id": campaign_id, "platforms": platforms, "state": "started"}


@router.get("/campaigns/{campaign_id}/media")
def media_status(campaign_id: str, db: Session = Depends(get_db)):
    camp = db.get(Campaign, campaign_id)
    if camp is None:
        raise HTTPException(404, "campaign not found")

    contents = db.query(PlatformContent).filter_by(campaign_id=campaign_id).all()
    scenes = (db.query(Scene).filter_by(campaign_id=campaign_id)
              .order_by(Scene.scene_order).all())
    assets = db.query(Asset).filter_by(campaign_id=campaign_id).all()

    step = camp.current_step or ""
    done = _ORDER.get(step, -1)
    progress = [
        {"name": s.split(":", 1)[1], "status": (
            "SUCCESS" if (camp.status == "SUCCESS" and step == "media:done") or _ORDER[s] < done
            else "RUNNING" if _ORDER[s] == done
            else "WAITING")}
        for s in MEDIA_STEPS
    ]

    cost_rows = (db.query(CostLog.kind, func.coalesce(func.sum(CostLog.amount_usd), 0.0))
                 .filter(CostLog.campaign_id == campaign_id).group_by(CostLog.kind).all())
    cost_by_kind = {k: round(float(v), 6) for k, v in cost_rows}

    render = max((a for a in assets if a.asset_type == "render"),
                 key=lambda a: a.created_at or a.id, default=None)
    thumbs = [a for a in assets if a.asset_type == "thumbnail"]

    # Video Studio Upgrade — creative plan + video QA (from the primary video
    # content's payload; absent until the media pipeline has run).
    _primary = next((c for c in contents if (c.payload or {}).get("creative_plan")), None)
    creative_plan = (_primary.payload or {}).get("creative_plan") if _primary else None
    video_qa = (_primary.payload or {}).get("video_qa") if _primary else None

    def scene_row(sc: Scene) -> dict:
        img = next((a for a in assets if a.scene_id == sc.id and a.asset_type == "image"), None)
        return {
            "scene_id": sc.id, "order": sc.scene_order, "narration": sc.narration,
            "duration": round(sc.estimated_duration, 2), "visual_type": sc.visual_type,
            "camera_motion": sc.camera_motion, "status": sc.generation_status,
            "provider": sc.generation_provider,
            "still": _rel(img.storage_path) if img else None,
        }

    previews = []
    for c in contents:
        spec = PLATFORMS.get(c.platform)
        c_assets = [a for a in assets if a.content_id == c.id]
        vid = max((a for a in c_assets if a.asset_type == "render"),
                  key=lambda a: a.created_at or a.id, default=None)
        imgs = [_rel(a.storage_path) for a in c_assets if a.asset_type in ("image", "carousel")]
        previews.append({
            "platform": c.platform, "label": spec.label if spec else c.platform,
            "family": spec.family.value if spec else "?", "status": c.status,
            "content_type": c.content_type, "aspect_ratio": c.aspect_ratio,
            "hook": c.hook, "caption": c.caption, "cta": c.cta,
            "hashtags": c.hashtags, "script": c.script,
            "video": _rel(vid.storage_path) if vid else None,
            "images": [i for i in imgs if i],
        })

    return {
        "campaign_id": campaign_id,
        "media_status": camp.status if step.startswith("media") else "PENDING",
        "current_step": step,
        "progress": progress,
        "scene_monitor": [scene_row(s) for s in scenes],
        "cost_by_kind": cost_by_kind,
        "cost_total": round(sum(cost_by_kind.values()), 6),
        "media_budget": get_settings().media_budget_usd,
        "render": {
            "video": _rel(render.storage_path) if render else None,
            "duration": render.duration if render else None,
            "width": render.width if render else None,
            "height": render.height if render else None,
            "qa": render.meta.get("qa") if render and render.meta else None,
        },
        "thumbnails": [_rel(t.storage_path) for t in thumbs],
        "previews": previews,
        "creative_plan": creative_plan,
        "video_qa": video_qa,
    }


@router.post("/campaigns/{campaign_id}/scenes/{scene_id}/regenerate")
def regenerate(campaign_id: str, scene_id: str, payload: RegenerateRequest,
               db: Session = Depends(get_db)):
    if db.get(Scene, scene_id) is None:
        raise HTTPException(404, "scene not found")
    from app.media.regen import regenerate_scene

    try:
        result = regenerate_scene(
            campaign_id, scene_id, visual_prompt=payload.visual_prompt,
            narration=payload.narration, camera_motion=payload.camera_motion,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return result
