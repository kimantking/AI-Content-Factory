from __future__ import annotations

import os
import statistics

import pytest

from app.agents.media_runner import run_media_pipeline
from app.db.base import session_scope
from app.db.models import Asset, Campaign, PlatformContent, Scene
from app.media.ffmpeg import probe

pytestmark = pytest.mark.integration


def test_short_video_end_to_end_fallback_path(ready_campaign, _base_settings):
    """Acceptance integration: Knowledge Pack -> ... -> final.mp4.
    No real AI-video provider => Image Motion FALLBACK. This is a FALLBACK PASS,
    not an AI_VIDEO REAL PASS."""
    cid = ready_campaign
    state = run_media_pipeline(cid, ["youtube_shorts", "instagram_carousel", "threads"])

    assert state["status"] in ("SUCCESS", "FIX_REQUIRED")
    assert state["media_qa"]["passed"] is True
    assert state["compliance"]["verdict"] != "BLOCK"
    assert state["content_qa"]["overall"] >= 0.6

    rp = state["render_path"]
    assert os.path.isfile(rp) and os.path.getsize(rp) > 100_000
    info = probe(rp)
    assert info["has_video"] and info["has_audio"]
    assert (info["width"], info["height"]) == (1080, 1920)
    assert info["duration"] >= 15

    with session_scope() as s:
        scenes = s.query(Scene).filter_by(campaign_id=cid).order_by(Scene.scene_order).all()
        assert len(scenes) >= 3
        durations = [sc.estimated_duration for sc in scenes]
        assert statistics.pstdev(durations) > 0.3            # editorial rhythm / burstiness
        assert len({sc.camera_motion for sc in scenes}) >= 3  # motion variety
        assert all(sc.visual_type != "AI_VIDEO" for sc in scenes)  # FALLBACK, no real video provider
        assert any(sc.visual_type in ("CHART", "TEXT_CARD", "STOCK_VIDEO") for sc in scenes)
        assert all(sc.generation_status == "SUCCESS" for sc in scenes)

        assets = s.query(Asset).filter_by(campaign_id=cid).all()
        kinds = {a.asset_type for a in assets}
        assert {"image", "audio", "subtitle", "render", "music"} <= kinds
        assert any(a.asset_type == "carousel" for a in assets)  # image-platform native asset

        contents = {c.platform: c for c in s.query(PlatformContent).filter_by(campaign_id=cid)}
        assert contents["threads"].script                       # text platform content object exists
        assert contents["threads"].status == "PLANNED"          # no publisher in Phase 1-B
        assert contents["youtube_shorts"].status in ("SUCCESS", "FIX_REQUIRED")

    # outputs/ has real files, not empty placeholders
    out_mp4 = os.path.join(_base_settings.output_root, cid, "youtube_shorts", "final.mp4")
    assert os.path.isfile(out_mp4) and os.path.getsize(out_mp4) > 100_000


def test_scene_regeneration_touches_only_one_scene(ready_campaign):
    cid = ready_campaign
    run_media_pipeline(cid, ["youtube_shorts"])
    with session_scope() as s:
        scenes = s.query(Scene).filter_by(campaign_id=cid).order_by(Scene.scene_order).all()
        target = scenes[1]
        target_id = target.id
        other_img_ids = {
            a.id for a in s.query(Asset).filter_by(campaign_id=cid, asset_type="image")
            if a.scene_id != target_id
        }

    from app.media.regen import regenerate_scene

    res = regenerate_scene(cid, target_id, narration="완전히 새로 쓴 이 장면의 내레이션입니다.",
                           camera_motion="PAN_DOWN")
    assert res["status"] in ("SUCCESS", "FIX_REQUIRED")

    with session_scope() as s:
        t = s.get(Scene, target_id)
        assert t.narration.startswith("완전히 새로")
        assert t.camera_motion == "PAN_DOWN"
        assert t.generation_status == "SUCCESS"
        still_there = {
            a.id for a in s.query(Asset).filter_by(campaign_id=cid, asset_type="image")
            if a.scene_id != target_id
        }
        assert still_there == other_img_ids            # other scenes' images untouched
