"""§CC / §A / §BC — Cross-Phase Intelligence API + one-screen compose."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.base import session_scope
from app.db.models import Campaign, PublishJob
from app.main import app

client = TestClient(app)


@pytest.fixture
def ws():
    return str(uuid.uuid4())


def test_add_references_and_library(ws):
    r = client.post("/api/references", json={
        "urls": ["https://example.com/mt-report", "https://example.com/ai-creators"],
        "execution_mode": "LEARN_ONLY", "workspace_id": ws, "topic": "AI 번역"})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "DONE" and body["result"]["mode"] == "LEARN_ONLY"
    assert len(body["references"]) == 2

    lib = client.get("/api/references", params={"workspace_id": ws}).json()
    assert len(lib) == 2

    dash = client.get("/api/learning", params={"workspace_id": ws}).json()
    assert dash["total_references"] == 2
    assert dash["dataset_records"] > 0

    gaps = client.get("/api/learning/gaps", params={"workspace_id": ws}).json()
    assert "recommendations" in gaps and gaps["library_counts"]


def test_ssrf_blocked_url_is_reported_not_fetched(ws):
    r = client.post("/api/references", json={
        "urls": ["http://169.254.169.254/latest/meta-data/", "http://localhost:6379/"],
        "execution_mode": "REFERENCE_ONLY", "workspace_id": ws})
    assert r.status_code == 201
    refs = r.json()["references"]
    assert all(x["status"] == "BLOCKED" for x in refs)
    assert all(x["support_level"] == "UNSUPPORTED" for x in refs)


def test_prompt_lab_test_promote_rollback(ws):
    client.post("/api/references", json={
        "urls": [f"https://batch.example.com/a{i}" for i in range(8)],
        "execution_mode": "LEARN_ONLY", "workspace_id": ws, "topic": "자동화",
        "purpose": "VIDEO_REFERENCE",
        "video_profiles": {f"https://batch.example.com/a{i}": _vp(i) for i in range(8)}})
    prompts = client.get("/api/learning/prompts", params={"workspace_id": ws}).json()
    assert prompts
    bid = prompts[0]["id"]

    detail = client.get(f"/api/learning/prompts/{bid}").json()
    assert detail["evidence"] and all(e["reference_id"] for e in detail["evidence"])

    prev = client.post(f"/api/learning/prompts/{bid}/test", json={"platform": "youtube_shorts"}).json()
    assert prev["preview_prompt"]

    # walk to VALIDATED then a user PROMOTE
    st = detail["status"]
    for nxt in ["OBSERVED", "EXPERIMENTAL", "CANDIDATE", "VALIDATED"][
            ["OBSERVED", "EXPERIMENTAL", "CANDIDATE", "VALIDATED"].index(st) + 1:]:
        assert client.post(f"/api/learning/prompts/{bid}/promote", json={"to_status": nxt}).status_code == 200
    assert client.post(f"/api/learning/prompts/{bid}/promote",
                       json={"to_status": "PROMOTED", "actor": "user"}).status_code == 200
    rb = client.post(f"/api/learning/prompts/{bid}/rollback").json()
    assert rb["status"] == "VALIDATED"


def test_platform_selection_endpoints(ws):
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="t", audience_goal="VIEWS", platforms=[], status="WAITING",
                        workspace_id=ws, execution_mode="CREATE_AND_LEARN"))
    r = client.post("/api/platform-selection", json={
        "campaign_id": cid,
        "selection": {"youtube_shorts": "GENERATE_AND_PUBLISH", "tiktok": "GENERATE_ONLY",
                      "instagram_reel": "DISABLED"}})
    assert r.status_code == 200
    body = r.json()
    assert set(body["generate_platforms"]) == {"youtube_shorts", "tiktok"}
    assert body["publish_platforms"] == ["youtube_shorts"]
    assert body["cost_preview"]["total_est_usd"] == "PRICING_UNKNOWN"

    got = client.get(f"/api/platform-selection/{cid}").json()
    assert got["selection"]["tiktok"]["VIDEO"] == "GENERATE_ONLY"

    presets = client.get("/api/platform-presets").json()
    assert any(p["name"] == "shortform_all" and p["builtin"] for p in presets)


def test_compose_learn_only_makes_no_campaign(ws):
    r = client.post("/api/campaigns/compose", json={
        "execution_mode": "LEARN_ONLY", "workspace_id": ws,
        "reference_urls": [f"https://batch.example.com/a{i}" for i in range(6)]})
    assert r.status_code == 201
    body = r.json()
    assert body["campaign_id"] is None and body["pipeline_started"] is False
    assert body["learning"]["ok"]
    with session_scope() as db:
        assert db.query(Campaign).count() == 0


def test_compose_create_and_learn_sets_selection_and_starts(ws, monkeypatch):
    started = {}

    def _fake_enqueue(camp):
        started["id"] = camp.id

    monkeypatch.setattr("app.api.routes_campaigns._enqueue", _fake_enqueue)
    r = client.post("/api/campaigns/compose", json={
        "execution_mode": "CREATE_AND_LEARN", "workspace_id": ws,
        "topic": "AI가 바꾸는 직업 5가지",
        "reference_urls": ["https://example.com/mt-report"],
        "platform_selection": {"youtube_shorts": "GENERATE_AND_PUBLISH",
                               "tiktok": "DISABLED", "linkedin": {"TEXT": "GENERATE_ONLY"}}})
    assert r.status_code == 201
    body = r.json()
    assert body["campaign_id"] and body["pipeline_started"] is True
    assert set(body["generate_platforms"]) == {"youtube_shorts", "linkedin"}
    assert started.get("id") == body["campaign_id"]
    with session_scope() as db:
        assert db.query(PublishJob).count() == 0     # pipeline enqueue was faked


def _vp(i):
    from tests.intel.conftest import video_profile
    return video_profile(i, common=True)
