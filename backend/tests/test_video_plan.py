"""Mock providers only; verify plan limits without paid generation."""
from pathlib import Path
from contextlib import contextmanager
import time

import pytest
from fastapi import HTTPException

from app.api.routes_intel import compose_campaign
from app.db.base import session_scope
from app.db.models import Campaign, PlatformContent, Scene
from app.services.budget import BudgetExceeded, check_media_budget


def test_plan_does_not_raise_existing_budget(_base_settings, make_campaign):
    cid = make_campaign()
    _base_settings.media_budget_usd = 1.5
    with session_scope() as db:
        camp = db.get(Campaign, cid)
        camp.video_mode, camp.video_plan = "VEO", "THREE_SCENES"
        db.flush()
        db.expire(camp)
        assert camp.video_plan == "THREE_SCENES"
        with pytest.raises(BudgetExceeded):
            check_media_budget(db, cid, pending_usd=3.2)
    assert _base_settings.media_budget_usd == 1.5


@pytest.mark.parametrize("invalid", ["UNLIMITED", {}, [], 3])
def test_invalid_plan_rejected_before_generation(invalid):
    with session_scope() as db:
        with pytest.raises(HTTPException) as exc:
            compose_campaign({"topic": "test", "video_mode": "VEO", "video_plan": invalid}, db)
        assert exc.value.status_code == 400


@pytest.mark.parametrize("plan,expected", [("PREVIEW", 1), ("THREE_SCENES", 3)])
def test_plan_caps_provider_calls_and_reuses_completed_clips(plan, expected, _base_settings, monkeypatch, tmp_path):
    from app.agents import media_nodes as nodes
    from app.providers.media.base import MediaResult
    from app.schemas.media import ProviderMode
    from app.providers.media.registry import get_storage

    _base_settings.storage_root = str(tmp_path)
    _base_settings.media_budget_usd = 20
    _base_settings.campaign_budget_usd = 20
    _base_settings.daily_budget_usd = 100
    _base_settings.monthly_budget_usd = 100
    get_storage.cache_clear()
    calls = []

    @contextmanager
    def short_idle_timeout():
        from sqlalchemy import text
        with session_scope() as db:
            db.execute(text("SET idle_in_transaction_session_timeout = '1s'"))
            try:
                yield db
                db.commit()
            finally:
                db.rollback()
                db.execute(text("SET idle_in_transaction_session_timeout = '60s'"))

    monkeypatch.setattr(nodes, "session_scope", short_idle_timeout)

    class Provider:
        def estimated_cost(self):
            return 3.2

        def generate_video(self, **kwargs):
            calls.append(kwargs)
            time.sleep(1.2)  # A slow provider must not leave a DB transaction idle.
            Path(kwargs["out_path"]).write_bytes(b"mock-video")
            return MediaResult(path=kwargs["out_path"], mime_type="video/mp4", provider="mock",
                               provider_mode=ProviderMode.MOCK, cost=3.2)

    monkeypatch.setattr(nodes, "get_video_provider", Provider)
    monkeypatch.setattr("app.media.ffmpeg.probe", lambda _: {"has_video": True, "duration": 8})
    with session_scope() as db:
        camp = Campaign(topic="test", video_mode="VEO", video_plan=plan)
        db.add(camp)
        db.flush()
        content = PlatformContent(campaign_id=camp.id, platform="youtube_shorts", content_type="SHORT_VIDEO")
        db.add(content)
        db.flush()
        scenes = []
        for order in range(4):
            scene = Scene(campaign_id=camp.id, content_id=content.id, scene_order=order, visual_type="AI_VIDEO")
            db.add(scene)
            db.flush()
            scenes.append({"id": scene.id, "scene_order": order, "visual_type": "AI_VIDEO", "estimated_duration": 5})
        state = {"campaign_id": camp.id, "content_id": content.id, "scenes": scenes}
    try:
        result = nodes.gen_videos_node(state)
        assert len(calls) == expected
        assert sum(bool(sc.get("video_path")) for sc in result["scenes"]) == expected
        assert all(sc["visual_type"] == "AI_IMAGE" for sc in result["scenes"][expected:])
        nodes.gen_videos_node(state)  # Original checkpoint may still contain AI_VIDEO.
        assert len(calls) == expected
    finally:
        get_storage.cache_clear()


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED"])
def test_terminal_media_step_is_not_running(status, make_campaign):
    from app.api.routes_media import media_status
    cid = make_campaign()
    with session_scope() as db:
        campaign = db.get(Campaign, cid)
        campaign.status, campaign.current_step = status, "media:videos"
        db.flush()
        result = media_status(cid, db)
        assert next(p for p in result["progress"] if p["name"] == "videos")["status"] == status


def test_image_success_is_not_video_success(make_campaign):
    from app.api.routes_media import media_status
    cid = make_campaign()
    with session_scope() as db:
        campaign = db.get(Campaign, cid)
        campaign.status, campaign.current_step = "RUNNING", "media:videos"
        content = PlatformContent(campaign_id=cid, platform="youtube_shorts", content_type="SHORT_VIDEO")
        db.add(content)
        db.flush()
        db.add(Scene(campaign_id=cid, content_id=content.id, scene_order=0,
                     visual_type="AI_VIDEO", generation_status="SUCCESS"))
        db.flush()
        assert media_status(cid, db)["scene_monitor"][0]["status"] == "PENDING"
