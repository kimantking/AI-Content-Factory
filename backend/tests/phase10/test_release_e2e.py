"""Phase 10 §86-§91, §96 — release-candidate E2E at the HTTP layer (the frontend
has no browser runner; Playwright would be a new dev dep needing D67). Covers the
Desktop + Mobile journeys through the same API the pages call, plus the
Support-Snapshot-under-failure and cross-device-state checks."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.base import session_scope
from app.db.models import Campaign, ErrorLog
from app.main import app
from app.ops.runtime_flags import _CACHE

pytestmark = [pytest.mark.phase10]
client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _flag_cache():
    _CACHE.clear()
    yield
    _CACHE.clear()


def test_rc_smoke_key_screens_respond():
    for path in ("/api/support/version", "/api/support/snapshot", "/api/support/snapshot.txt",
                 "/api/ops/config-check", "/api/library", "/api/config",
                 "/api/governance/review", "/api/publishing/calendar"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
    assert client.get("/api/support/version").json()["version"] == "1.0.0"


def test_desktop_and_mobile_journey_create_to_snapshot():
    # Quick Create (same call for desktop + mobile viewports)
    r = client.post("/api/campaigns", json={"topic": "릴리스 후보 검증", "goal": "BALANCED",
                                            "platforms": ["youtube_shorts"]})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert client.get(f"/api/campaigns/{cid}").json()["status"] in ("SUCCESS", "DONE", "COMPLETE")
    # library shows it
    assert any(c["campaign_id"] == cid for c in client.get("/api/library").json()["items"])
    # support snapshot focuses it and has a real routing record
    snap = client.get("/api/support/snapshot", params={"campaign_id": cid}).json()
    assert snap["version"] == "1.0.0"
    assert snap["model_routing"]["last_route"] is not None
    txt = client.get("/api/support/snapshot.txt", params={"campaign_id": cid}).text
    assert "SUPPORT SNAPSHOT" in txt and 15 <= len(txt.splitlines()) <= 90


def test_cross_device_state_is_shared_via_backend():
    """A campaign created 'on desktop' is the same object 'on mobile' — same
    backend, same DB, no client-only state."""
    r = client.post("/api/campaigns", json={"topic": "크로스 디바이스", "goal": "BALANCED",
                                            "platforms": ["youtube_shorts"]})
    cid = r.json()["id"]
    d1 = client.get(f"/api/campaigns/{cid}").json()
    d2 = client.get(f"/api/campaigns/{cid}").json()
    assert d1["status"] == d2["status"] and d1["current_step"] == d2["current_step"]
    # a snapshot from any device shows the same governance/cost
    s = client.get("/api/support/snapshot", params={"campaign_id": cid}).json()
    assert s["governance"]["state"] == d1["status"]


def test_mobile_emergency_pause_stops_publish_then_releases():
    from app.db.models import PublishJob
    from app.publishing.engine import run_publish_job
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="emergency", audience_goal="BALANCED",
                        platforms=["naver_blog"], status="SUCCESS"))
        db.flush()
        j = PublishJob(campaign_id=cid, platform="naver_blog", content_type="post",
                       status="READY", run_mode="MANUAL", approval_status="APPROVED",
                       idempotency_key=str(uuid.uuid4()))
        db.add(j)
        db.flush()
        jid = j.id
    # "authorized mobile user" flips the switch through the ops API
    assert client.post("/api/ops/flags/GLOBAL_PUBLISH_PAUSE",
                       json={"enabled": True, "confirm": True}).status_code == 200
    _CACHE.clear()
    res = run_publish_job(jid)
    assert res.get("publish_paused") is True
    with session_scope() as db:
        assert db.get(PublishJob, jid).remote_post_id is None
    # release
    client.post("/api/ops/flags/GLOBAL_PUBLISH_PAUSE", json={"enabled": False, "confirm": True})
    _CACHE.clear()
    assert run_publish_job(jid).get("publish_paused") is not True


def test_support_snapshot_reflects_a_failure_with_action():
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="장애 스냅샷", audience_goal="BALANCED",
                        platforms=["youtube_shorts"], status="FAILED"))
        db.flush()
        db.add(ErrorLog(campaign_id=cid, scope="ollama", error_type="PROVIDER_ERROR",
                        message="ollama connection refused"))
    s = client.get("/api/support/snapshot", params={"campaign_id": cid}).json()
    assert s["last_error"]["error_code"] == "OLLAMA_UNAVAILABLE"
    assert "Ollama" in s["last_error"]["suggested_action"]
    assert s["overall_health"] in ("OK", "DEGRADED", "ERROR")
