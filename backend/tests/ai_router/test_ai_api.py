"""§13, §17, §31, §32, §23 — Local AI + Model Router + Cost + Benchmark API."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_local_ai_status_never_500(_base_settings):
    _base_settings.ollama_enabled = False
    r = client.get("/api/local-ai/status")
    assert r.status_code == 200 and r.json()["status"] == "DISABLED"


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
