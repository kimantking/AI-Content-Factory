from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import session_scope
from app.db.models import Asset, Campaign, PlatformContent, Scene, Script, VerifiedFact
from app.governance.licenses import seed_license_registry
from app.governance.policy import seed_policy_registry
from app.governance.rights import record_asset_rights


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _seed_registries(_base_settings):
    with session_scope() as db:
        seed_license_registry(db)
        seed_policy_registry(db)
    yield


def _mk_scene(db, cid, content_id, order, narr, vtype="AI_IMAGE"):
    s = Scene(campaign_id=cid, content_id=content_id, scene_order=order,
              narration=narr, estimated_duration=4.0 + order * 0.3, visual_type=vtype,
              camera_motion=["SLOW_ZOOM_IN", "KEN_BURNS", "PAN_LEFT", "PAN_RIGHT"][order % 4],
              music_energy="mid", generation_status="SUCCESS")
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def governed_campaign(_base_settings, tmp_path):
    """A tenant-scoped campaign with a script, 5 scenes, a render asset, and a
    RightsLedger entry per media asset. Returns ids + a helper to add assets."""
    ws = str(uuid.uuid4())
    brand = str(uuid.uuid4())
    channel = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    render_path = str(tmp_path / "final.mp4")
    open(render_path, "wb").write(b"\x00" * 200_000)

    with session_scope() as db:
        db.add(Campaign(id=cid, topic="AI가 바꾸는 직업 지형", audience_goal="VIEWS",
                        platforms=["youtube_shorts"], status="SUCCESS",
                        workspace_id=ws, brand_id=brand, channel_id=channel))
        db.add(Script(campaign_id=cid, platform="MASTER",
                      body=("AI가 일부 직업을 빠르게 바꾸고 있다. 번역 같은 반복 업무는 자동화가 빠르게 진행된다. "
                            "하지만 돌봄 노동은 자동화가 느리다. 정리하면, 지금 한 가지 업무를 자동화해보라."),
                      word_count=40, qa_passed=True, qa_report={}, ai_slop_score=12.0,
                      naturalness={}))
        content = PlatformContent(campaign_id=cid, platform="youtube_shorts",
                                  content_type="SHORT_VIDEO", hook="AI가 바꾸는 직업",
                                  title="AI가 바꾸는 직업 지형", caption="", script="본문",
                                  status="PLANNED", payload={})
        db.add(content)
        db.flush()
        content_id = content.id
        for f, st in (("번역 같은 반복 업무는 자동화가 빠르다", "VERIFIED"),
                      ("돌봄 노동은 자동화가 느리다", "VERIFIED")):
            db.add(VerifiedFact(campaign_id=cid, fact=f, status=st, confidence=0.85,
                                source_ids=["s1"], reason="복수 출처"))
        for i, (narr, vt) in enumerate([
            ("AI가 일부 직업을 빠르게 바꾸고 있다", "AI_IMAGE"),
            ("통계에 따르면 번역 수요가 20% 감소했다", "CHART"),
            ("하지만 돌봄 노동은 자동화가 느리다", "STOCK_VIDEO"),
            ("정리하면 지금 한 가지 업무를 자동화해보라", "TEXT_CARD"),
            ("다음 편에서 구체적인 방법을 다룬다", "AI_IMAGE"),
        ]):
            _mk_scene(db, cid, content_id, i, narr, vt)
        render = Asset(campaign_id=cid, content_id=content_id, asset_type="render",
                       provider="ffmpeg", provider_mode="REAL", prompt="", storage_path=render_path,
                       mime_type="video/mp4", width=1080, height=1920, duration=22.0, status="SUCCESS",
                       meta={"platform": "youtube_shorts"})
        db.add(render)
        db.flush()

    def add_asset(*, asset_type="image", source_type="AI_GENERATED", **rights_kw):
        with session_scope() as db:
            a = Asset(campaign_id=cid, content_id=content_id, asset_type=asset_type,
                      provider=rights_kw.get("source_provider", "mock"), provider_mode="MOCK",
                      prompt="", storage_path=str(tmp_path / f"{asset_type}_{uuid.uuid4().hex[:6]}.bin"),
                      mime_type="application/octet-stream", status="SUCCESS", meta={})
            db.add(a)
            db.flush()
            led = record_asset_rights(
                db, asset_id=a.id, source_type=source_type, workspace_id=ws, brand_id=brand,
                channel_id=channel, campaign_id=cid, **rights_kw)
            return {"asset_id": a.id, "rights_id": led.id, "rights_status": led.rights_status}

    return {"workspace_id": ws, "brand_id": brand, "channel_id": channel,
            "campaign_id": cid, "content_id": content_id, "render_path": render_path,
            "add_asset": add_asset, "tmp_path": tmp_path}
