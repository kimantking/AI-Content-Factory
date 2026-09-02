"""Content Library API (Phase 8)."""
from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.library import add_platform_to_campaign, content_detail, library_stats, list_content
from app.library.search import global_search

router = APIRouter(prefix="/api", tags=["library"])


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    workspace_id: str | None = None,
    kinds: str | None = Query(None, description="comma-separated: campaign,platform_content,channel,brand,reference,publication"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """AUDIT-P8-003 — unified global search across campaigns / platform content /
    channels / brands / learning references / publications."""
    kind_list = [k.strip() for k in kinds.split(",") if k.strip()] if kinds else None
    return global_search(db, q=q, workspace_id=workspace_id, kinds=kind_list, limit=limit)


@router.get("/library")
def library(
    workspace_id: str | None = None, brand_id: str | None = None, channel_id: str | None = None,
    platform: str | None = None, content_type: str | None = None, status: str | None = None,
    governance: str | None = None, publish_state: str | None = None,
    q: str | None = Query(None), sort: str = "newest", page: int = 1, page_size: int | None = None,
    db: Session = Depends(get_db),
):
    return list_content(db, workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id,
                        platform=platform, content_type=content_type, status=status,
                        governance=governance, publish_state=publish_state, query=q, sort=sort,
                        page=page, page_size=page_size)


@router.get("/library/stats")
def stats(workspace_id: str | None = None, db: Session = Depends(get_db)):
    return library_stats(db, workspace_id=workspace_id)


@router.get("/library/{campaign_id}")
def detail(campaign_id: str, db: Session = Depends(get_db)):
    d = content_detail(db, campaign_id)
    if d is None:
        raise HTTPException(404, "content not found")
    return d


@router.get("/library/{campaign_id}/{tab}")
def detail_tab(campaign_id: str, tab: str, db: Session = Depends(get_db)):
    d = content_detail(db, campaign_id)
    if d is None:
        raise HTTPException(404, "content not found")
    if tab not in d:
        raise HTTPException(404, f"unknown tab {tab}")
    return {tab: d[tab]}


@router.get("/library/{campaign_id}/media/{asset_type}")
def media_file(campaign_id: str, asset_type: str, db: Session = Depends(get_db)):
    """Stream a real media file (video preview) if it exists on disk."""
    d = content_detail(db, campaign_id)
    if d is None:
        raise HTTPException(404, "content not found")
    if asset_type in ("video", "render"):
        p = d["preview"]["video_path"]
        if not p or not os.path.isfile(p):
            raise HTTPException(404, "no playable file")
        return FileResponse(p, media_type="video/mp4", filename=os.path.basename(p))
    for a in d["media"]:
        if a["asset_type"] == asset_type and a["exists"]:
            return FileResponse(a["path"], filename=os.path.basename(a["path"]))
    raise HTTPException(404, "no file")


@router.post("/library/{campaign_id}/add-platform")
def add_platform(campaign_id: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    res = add_platform_to_campaign(db, campaign_id=campaign_id,
                                   platform=payload["platform"],
                                   mode=payload.get("mode", "GENERATE_AND_PUBLISH"))
    if not res.get("ok"):
        raise HTTPException(409, res.get("error", "cannot add platform"))
    db.commit()
    return res


@router.post("/library/{campaign_id}/edit-plan")
def edit_plan(campaign_id: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    """AUDIT-P8-002 — translate a natural-language edit into a structured
    EditRequest and preview its Smart-Rerender impact. Does NOT render."""
    from app.edit import apply_edit, impact_of, parse_instruction
    from app.edit.scene_io import load_scene_state

    old_scenes, meta = load_scene_state(db, campaign_id)
    if not old_scenes:
        raise HTTPException(404, "no scenes for this campaign")
    req = parse_instruction(payload.get("instruction", ""))
    if not req.ops:
        return {"instruction": payload.get("instruction", ""), "request": req.as_dict(),
                "impact": None, "note": "no recognised edit in the instruction"}
    new_scenes, new_meta = apply_edit(old_scenes, meta, req)
    return {
        "instruction": payload.get("instruction", ""),
        "request": req.as_dict(),
        "impact": impact_of(old_scenes, new_scenes, old_meta=meta, new_meta=new_meta),
    }
