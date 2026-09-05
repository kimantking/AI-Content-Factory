"""§34-§46 — Content Library API."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.base import session_scope
from app.db.models import Asset, Campaign, PlatformContent
from app.main import app

client = TestClient(app)


@pytest.fixture
def sample(tmp_path):
    cid = str(uuid.uuid4())
    mp4 = tmp_path / "r.mp4"
    mp4.write_bytes(b"\x00" * 40_000)
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="라이브러리 API 테스트", audience_goal="VIEWS",
                        platforms=["youtube_shorts"], status="SUCCESS"))
        db.flush()
        c = PlatformContent(campaign_id=cid, platform="youtube_shorts", content_type="SHORT_VIDEO",
                            title="t", script="s", status="PLANNED", payload={})
        db.add(c)
        db.flush()
        db.add(Asset(campaign_id=cid, content_id=c.id, asset_type="render", provider="ffmpeg",
                     provider_mode="REAL", storage_path=str(mp4), mime_type="video/mp4",
                     duration=12.0, status="SUCCESS", meta={"fps": 30}))
    return cid, str(mp4)


def test_library_list_and_detail(sample):
    cid, _ = sample
    lst = client.get("/api/library").json()
    assert any(x["campaign_id"] == cid for x in lst["items"])
    assert "page" in lst and "pages" in lst

    d = client.get(f"/api/library/{cid}").json()
    assert d["overview"]["topic"] == "라이브러리 API 테스트"
    assert d["preview"]["video_playable"] is True

    tab = client.get(f"/api/library/{cid}/media").json()
    assert "media" in tab and tab["media"][0]["asset_type"] == "render"


def test_library_video_stream(sample):
    cid, _ = sample
    r = client.get(f"/api/library/{cid}/media/video")
    assert r.status_code == 200 and r.headers["content-type"].startswith("video/mp4")


def test_library_stats(sample):
    s = client.get("/api/library/stats").json()
    assert s["total_campaigns"] >= 1 and s["campaigns_with_video"] >= 1


def test_add_platform_endpoint(sample):
    cid, _ = sample
    r = client.post(f"/api/library/{cid}/add-platform", json={"platform": "tiktok"})
    assert r.status_code == 200 and r.json()["added"] == "tiktok"
    dup = client.post(f"/api/library/{cid}/add-platform", json={"platform": "tiktok"})
    assert dup.status_code == 409


def test_delete_content_removes_campaign_and_children(sample):
    cid, _ = sample
    r = client.delete(f"/api/library/{cid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert client.get(f"/api/library/{cid}").status_code == 404
    with session_scope() as db:
        assert db.get(Campaign, cid) is None
        assert db.query(Asset).filter_by(campaign_id=cid).count() == 0


def test_delete_running_content_stops_then_deletes(monkeypatch):
    from app.api import routes_campaigns

    monkeypatch.setattr(routes_campaigns, "_revoke_campaign_tasks", lambda _cid: ["running-task"])
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="진행 중", audience_goal="VIEWS",
                        platforms=["youtube_shorts"], status="RUNNING"))
    response = client.delete(f"/api/library/{cid}")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert client.get(f"/api/library/{cid}").status_code == 404


def test_missing_content_404():
    assert client.get(f"/api/library/{uuid.uuid4()}").status_code == 404
