"""§91-§93 — Phase 8 integrated flows (no media pipeline; mock providers).

Beginner create -> Content Library discovery -> cost preview -> routing telemetry.
Learning-only -> no production -> library shows it as learn-only.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.ai_router.execute import run_routed
from app.db.base import session_scope
from app.db.models import Campaign, PublishJob
from app.db.models_p8 import ModelRoutingEvent
from app.main import app

client = TestClient(app)


def test_beginner_create_lands_in_content_library(_base_settings):
    _base_settings.ollama_enabled = True
    ws = str(uuid.uuid4())

    # cost preview before creating
    cost = client.post("/api/cost/estimate", json={
        "selection": {"youtube_shorts": "GENERATE_AND_PUBLISH", "tiktok": "DISABLED"},
        "quality_preset": "balanced", "execution_mode": "CREATE_AND_LEARN"}).json()
    assert cost["categories"]["Video"]["state"] == "UNKNOWN"        # honest, not fabricated
    assert "youtube_shorts" in cost["generate_platforms"]

    # one-screen compose (topic only, no refs -> fast)
    r = client.post("/api/campaigns/compose", json={
        "topic": "AI 때문에 바뀌는 직업 5가지", "execution_mode": "CREATE_ONLY",
        "workspace_id": ws,
        "platform_selection": {"youtube_shorts": "GENERATE_AND_PUBLISH",
                               "instagram_reel": "DISABLED"}})
    assert r.status_code == 201
    cid = r.json()["campaign_id"]
    assert cid and set(r.json()["generate_platforms"]) == {"youtube_shorts"}

    # appears in the Content Library, scoped to the workspace
    lib = client.get("/api/library", params={"workspace_id": ws}).json()
    assert any(x["campaign_id"] == cid for x in lib["items"])
    card = next(x for x in lib["items"] if x["campaign_id"] == cid)
    assert card["legacy"] is False and card["execution_mode"] == "CREATE_ONLY"
    assert card["platforms"] == ["youtube_shorts"]

    detail = client.get(f"/api/library/{cid}").json()
    assert detail["overview"]["governance"] in ("NONE", "NOT_APPLICABLE", "OK")


def test_routing_telemetry_recorded_for_a_real_task(_base_settings):
    _base_settings.ollama_enabled = True    # local model is the chosen engine
    with session_scope() as db:
        run_routed(db, agent_type="Data Curator", task_type="classification",
                   system="Classify. Return {\"label\": \"NEWS\"}.",
                   user="The central bank raised rates.", workspace_id="wsX")
    with session_scope() as db:
        evs = db.query(ModelRoutingEvent).filter_by(workspace_id="wsX").all()
        assert evs, "a routing event should be recorded (success or failure)"
        assert evs[0].task_type == "classification" and evs[0].tier == "local_light"


def test_learn_only_via_compose_makes_no_production(_base_settings):
    ws = str(uuid.uuid4())
    r = client.post("/api/campaigns/compose", json={
        "execution_mode": "LEARN_ONLY", "workspace_id": ws,
        "reference_urls": []})
    assert r.status_code == 201
    assert r.json()["campaign_id"] is None and r.json()["pipeline_started"] is False
    with session_scope() as db:
        assert db.query(Campaign).filter_by(workspace_id=ws).count() == 0
        assert db.query(PublishJob).count() == 0
