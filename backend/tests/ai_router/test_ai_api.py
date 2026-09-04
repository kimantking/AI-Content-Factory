"""§13, §17, §31, §32, §23 — Local AI + Model Router + Cost + Benchmark API."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_local_ai_status_never_500(_base_settings):
    _base_settings.ollama_enabled = False
    r = client.get("/api/local-ai/status")
    assert r.status_code == 200 and r.json()["status"] == "DISABLED"


def test_agent_chat_works_in_mock_mode(_base_settings):
    _base_settings.ollama_enabled = False
    r = client.post("/api/agents/research/chat", json={"message": "이번 주제를 어떻게 조사할까요?", "history": []})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] and body["agent_id"] == "research" and body["mock"] is True


def test_agent_chat_accepts_sanitized_campaign_context(_base_settings):
    _base_settings.ollama_enabled = False
    r = client.post("/api/agents/script/chat", json={
        "message": "지금 작업에 맞춰 알려줘",
        "campaign_context": {"topic": "부산 여행 숏폼", "stage": "SCRIPT", "ignored": {"secret": "x"}},
    })
    assert r.status_code == 200 and r.json()["agent_id"] == "script"


def test_agent_chat_rejects_unknown_agent(_base_settings):
    r = client.post("/api/agents/unknown/chat", json={"message": "안녕"})
    assert r.status_code == 404


def test_agent_chat_uses_local_only_routing_when_ollama_enabled(_base_settings, monkeypatch):
    from app.api import routes_ai

    captured = {}

    class Result:
        data = {"reply": "로컬 응답"}
        text = ""
        provider = "ollama"
        model_id = "gemma3:4b"
        error = None

    def fake_run(*_args, **kwargs):
        captured.update(kwargs)
        return Result()

    _base_settings.ollama_enabled = True
    monkeypatch.setattr(routes_ai, "run_routed", fake_run)
    r = client.post("/api/agents/research/chat", json={"message": "테스트"})
    assert r.status_code == 200
    assert r.json()["provider"] == "ollama"
    assert captured["privacy"] == "local_only"
    assert "핵심 근거는 최대 5개" in captured["system"]
    assert "영상에 쓸 핵심" in captured["system"]
    assert captured["context"]["max_tokens"] == 700


def test_local_ai_status_reports_not_running_when_unreachable(_base_settings):
    _base_settings.ollama_enabled = True
    _base_settings.ollama_base_url = "http://127.0.0.1:59998"
    r = client.get("/api/local-ai/status")
    assert r.status_code == 200
    assert r.json()["status"] in ("NOT_RUNNING", "DEGRADED")


def test_models_endpoint_lists_python_local_and_cloud(_base_settings):
    _base_settings.ollama_enabled = True
    rows = client.get("/api/models").json()
    ids = {m["model_id"] for m in rows}
    assert "python" in ids and any(m["kind"] == "local" for m in rows)


def test_route_preview_differs_by_task(_base_settings):
    _base_settings.ollama_enabled = True
    cheap = client.post("/api/models/route", json={"agent_type": "Data Curator",
                                                   "task_type": "classification"}).json()
    prem = client.post("/api/models/route", json={"agent_type": "Hook Agent",
                                                  "task_type": "hook"}).json()
    det = client.post("/api/models/route", json={"agent_type": "Fact Checker",
                                                 "task_type": "hash"}).json()
    assert cheap["tier"] == "local_light" and prem["tier"] == "premium"
    assert det["deterministic"] is True and det["selected_model"] == "python"
    # routing genuinely differs by task (tier), not just a label; with no cloud key
    # the premium task correctly falls back to local rather than a fake premium name
    assert cheap["tier"] != prem["tier"]
    assert prem["selected_model"] in ("claude-sonnet-5", "gemma3:4b", "")


def test_cost_estimate_endpoint(_base_settings):
    _base_settings.ollama_enabled = True
    r = client.post("/api/cost/estimate", json={
        "selection": {"youtube_shorts": "GENERATE_AND_PUBLISH"}, "quality_preset": "balanced"}).json()
    assert "categories" in r and r["categories"]["Video"]["state"] == "UNKNOWN"
    assert r["has_unknown"] is True


def test_benchmark_runs_on_mock_and_records_performance(_base_settings):
    # mock LLM path -> MOCK_VERIFIED, still exercises the plumbing + writes rows
    _base_settings.ollama_enabled = False
    r = client.post("/api/models/benchmark", json={"model_id": "claude-haiku-4-5-20251001",
                                                   "provider": "anthropic"}).json()
    assert r["ok"] is True and r["verified"] in ("MOCK_VERIFIED", "CLOUD_VERIFIED")
    perf = client.get("/api/models/performance").json()
    assert any(p["model_id"] == "claude-haiku-4-5-20251001" for p in perf)
