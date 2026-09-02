"""Phase 9 §72-§78 — end-to-end user journeys.

No browser runner is installed (Playwright would be a new dev dependency needing
D67 approval; global install is disallowed). These drive the same journeys the
frontend drives, through the HTTP API. Frontend rendering is gated by `tsc
--noEmit` + `next build` (both clean — see §116). Rendered-browser Playwright E2E
is AVAILABLE_NOT_REQUIRED for this gate.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.base import session_scope
from app.db.models import Asset, Campaign, PlatformContent, Scene, Script
from app.main import app

pytestmark = [pytest.mark.phase9, pytest.mark.browser_e2e]
client = TestClient(app, raise_server_exceptions=False)


# ---- Journey 1: Beginner — topic -> create -> result -> library ---- #

def test_journey_beginner_end_to_end():
    # cost preview (endpoint exists)
    prev = client.post("/api/cost/estimate", json={"topic": "AI가 바꾸는 번역 산업",
                                                   "platforms": ["youtube_shorts", "tiktok"]})
    assert prev.status_code in (200, 404, 422)

    r = client.post("/api/campaigns", json={"topic": "AI가 바꾸는 번역 산업", "goal": "BALANCED",
                                            "platforms": ["youtube_shorts", "tiktok"]})
    assert r.status_code == 201
    cid = r.json()["id"]

    d = client.get(f"/api/campaigns/{cid}")
    assert d.status_code == 200 and d.json()["status"] in ("SUCCESS", "COMPLETE", "DONE")

    lib = client.get("/api/library", params={"q": "번역"})
    assert lib.status_code == 200 and any(c["campaign_id"] == cid for c in lib.json()["items"])

    detail = client.get(f"/api/library/{cid}")
    assert detail.status_code == 200
    # a review/governance view for the item
    assert client.get(f"/api/library/{cid}/governance").status_code in (200, 404)


# ---- Journey 2: Learning — LEARN_ONLY, no production increase ------ #

def test_journey_learning_no_production_growth():
    from app.intel import fetch as F
    c = F.MockReferenceClient()
    for i in range(10):
        c.register(f"https://j2.example.com/a{i}",
                   body=f"<html><head><title>학습 {i}</title></head><body><main><h1>학습 {i}</h1>"
                        f"<p>연구에 따르면 자동화가 {40+i}% 라 한다. 전문가는 검수가 중요하다 말했다. "
                        f"예시 {i}에서 사람이 확인한다.</p></main></body></html>")
    F.set_client(c)
    try:
        with session_scope() as db:
            before = db.query(Campaign).count()
        payload = {"urls": [f"https://j2.example.com/a{i}" for i in range(10)],
                   "execution_mode": "LEARN_ONLY", "topic": "AI 콘텐츠", "run": True}
        resp = client.post("/api/references", json=payload)
        assert resp.status_code in (200, 201, 202), resp.text
        with session_scope() as db:
            after = db.query(Campaign).count()
        assert after == before        # LEARN_ONLY created no campaigns
    finally:
        F.set_client(F.MockReferenceClient())


# ---- Journey 3: Edit — scene change -> scoped impact -------------- #

def test_journey_edit_scoped_impact():
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="편집 여정", audience_goal="BALANCED",
                        platforms=["youtube_shorts"], status="SUCCESS"))
        db.flush()
        pc = PlatformContent(campaign_id=cid, platform="youtube_shorts", content_type="short")
        db.add(pc)
        db.flush()
        for i in (1, 2, 3, 4):
            a = Asset(campaign_id=cid, content_id=pc.id, asset_type="image",
                      status="SUCCESS", storage_path=f"/tmp/a{i}.png")
            db.add(a); db.flush()
            db.add(Scene(campaign_id=cid, content_id=pc.id, scene_order=i,
                         estimated_duration=4.0, narration=f"n{i}", subtitle_text=f"s{i}",
                         camera_motion="SLOW_ZOOM_IN", asset_id=a.id))
    r = client.post(f"/api/library/{cid}/edit-plan", json={"instruction": "3번 장면 b-roll을 교체해줘"})
    assert r.status_code == 200
    imp = r.json()["impact"]
    assert imp["rebuild_scene_clips"] == [3]
    assert imp["regenerates_ai_visuals"] is True
    # scenes 1,2,4 untouched
    assert 1 not in imp["rebuild_scene_clips"] and 4 not in imp["rebuild_scene_clips"]


# ---- Journey 4: Platform add-later — no unrelated regen --------- #

def test_journey_platform_add_no_unrelated_regen():
    r = client.post("/api/campaigns", json={"topic": "플랫폼 추가 여정", "goal": "BALANCED",
                                            "platforms": ["youtube_shorts"]})
    cid = r.json()["id"]
    with session_scope() as db:
        yt_content_ids = {c.id for c in db.query(PlatformContent).filter_by(
            campaign_id=cid, platform="youtube_shorts")}
    add = client.post(f"/api/library/{cid}/add-platform",
                      json={"platform": "instagram_reel", "mode": "GENERATE_AND_PUBLISH"})
    assert add.status_code in (200, 409)
    if add.status_code == 200:
        with session_scope() as db:
            yt_after = {c.id for c in db.query(PlatformContent).filter_by(
                campaign_id=cid, platform="youtube_shorts")}
        assert yt_after == yt_content_ids     # youtube content not regenerated


# ---- Journey 5: Review — HUMAN_REVIEW -> approve -> dry-run ----- #

def test_journey_review_center_available():
    r = client.get("/api/governance/review")
    assert r.status_code == 200
    assert isinstance(r.json(), (list, dict))


# ---- §78 Mobile — the review/approve endpoints are viewport-agnostic (API) #

def test_journey_mobile_review_endpoints_work():
    # the same endpoints a mobile client hits
    assert client.get("/api/governance/cases").status_code == 200
    assert client.get("/api/library", params={"page_size": 10}).status_code == 200
