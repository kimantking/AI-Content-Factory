from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
TOPIC = "AI로 사라질 가능성이 높은 직업"


def test_health_and_config():
    assert client.get("/health").json()["status"] == "ok"
    cfg = client.get("/api/config").json()
    assert cfg["phase"] == "1-A"
    assert "YouTube" in cfg["platforms"]
    assert cfg["natural_content"]["max_ai_slop_score"] == 20


def test_open_source_endpoint():
    rows = client.get("/api/open-source-components").json()
    assert any(r["name"] == "whisperX" for r in rows)


def test_agent_reach_status_is_safe_when_binary_missing(monkeypatch):
    from app.api import routes_meta

    monkeypatch.setattr(routes_meta.shutil, "which", lambda _name: None)
    body = client.get("/api/agent-reach/status").json()
    assert body == {"installed": False, "status": "NOT_INSTALLED", "channels": {}}


def test_create_campaign_runs_inline_and_detail_is_complete(_base_settings):
    _base_settings.run_inline = True
    r = client.post("/api/campaigns", json={"topic": TOPIC, "audience_goal": "VIEWS",
                                            "platforms": ["YouTube", "TikTok"]})
    assert r.status_code == 201
    cid = r.json()["id"]

    detail = client.get(f"/api/campaigns/{cid}").json()
    assert detail["status"] == "SUCCESS"
    assert detail["audience_goal"] == "VIEWS"
    assert len(detail["hooks"]) >= 3
    assert detail["script"]["qa_passed"] is True
    assert detail["script"]["ai_slop_score"] <= 20
    assert detail["knowledge_pack"]["verified_facts"]
    assert any(s["status"] == "SUCCESS" for s in detail["steps"])
    assert detail["cost_usd"] == 0.0  # mock
    assert detail["budget"]["campaign"] > 0


def test_unknown_campaign_404():
    assert client.get("/api/campaigns/does-not-exist").status_code == 404
