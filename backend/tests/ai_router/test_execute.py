"""§21, §32, §80, §81 — run_routed: escalation, fallback, LOCAL_ONLY, telemetry."""
from __future__ import annotations

import pytest

from app.ai_router import execute as ex
from app.ai_router.router import ModelRouter
from app.db.base import session_scope
from app.db.models_p8 import ModelRoutingEvent
from app.providers.errors import ProviderError
from tests.ai_router.conftest import RecordingProvider


@pytest.fixture
def wire(monkeypatch, full_registry):
    """Patch the router registry + provider factory with recorders."""
    local = RecordingProvider("ollama", "gemma3:4b", payload={"label": "NEWS", "confidence": 0.9})
    cheap = RecordingProvider("anthropic", "claude-haiku-4-5-20251001", payload={"label": "NEWS"})
    prem = RecordingProvider("anthropic", "claude-sonnet-5", payload={"hook": "강력한 훅"})
    reg = {"gemma3:4b": local, "claude-haiku-4-5-20251001": cheap, "claude-sonnet-5": prem}

    monkeypatch.setattr(ex.ModelRouter, "__init__",
                        lambda self, registry=None: setattr(self, "reg", full_registry))
    monkeypatch.setattr(ex, "_provider_for", lambda mid, prov: reg[mid.split("@")[0]])
    return {"local": local, "cheap": cheap, "prem": prem}


def test_cheap_task_never_calls_premium(wire):
    with session_scope() as db:
        r = ex.run_routed(db, agent_type="Data Curator", task_type="classification",
                          system="classify", user="the central bank raised rates")
    assert r.model_id == "gemma3:4b" and r.data["label"] == "NEWS"
    assert wire["local"].calls and not wire["prem"].calls and not wire["cheap"].calls


def test_premium_task_uses_premium_model(wire):
    with session_scope() as db:
        r = ex.run_routed(db, agent_type="Hook Agent", task_type="hook",
                          system="write a hook", user="AI 번역")
    assert r.model_id == "claude-sonnet-5" and r.data["hook"]
    assert wire["prem"].calls and not wire["local"].calls


def test_schema_invalid_escalates_to_next_engine(monkeypatch, full_registry):
    bad_local = RecordingProvider("ollama", "gemma3:4b", bad_json=True)
    good_cheap = RecordingProvider("anthropic", "claude-haiku-4-5-20251001", payload={"label": "OK"})
    reg = {"gemma3:4b": bad_local, "claude-haiku-4-5-20251001": good_cheap,
           "claude-sonnet-5": RecordingProvider("anthropic", "claude-sonnet-5", payload={"label": "OK"})}
    monkeypatch.setattr(ex.ModelRouter, "__init__",
                        lambda self, registry=None: setattr(self, "reg", full_registry))
    monkeypatch.setattr(ex, "_provider_for", lambda mid, prov: reg[mid.split("@")[0]])
    with session_scope() as db:
        r = ex.run_routed(db, agent_type="Data Curator", task_type="classification",
                          system="c", user="u")
    assert r.escalated is True and r.fallback_used is True
    assert r.model_id in ("claude-haiku-4-5-20251001", "claude-sonnet-5")
    assert bad_local.calls and good_cheap.calls


def test_local_failure_falls_back_when_cloud_allowed(monkeypatch, full_registry):
    dead_local = RecordingProvider("ollama", "gemma3:4b",
                                   raise_error=ProviderError("connection refused"))
    cloud = RecordingProvider("anthropic", "claude-haiku-4-5-20251001", payload={"label": "OK"})
    reg = {"gemma3:4b": dead_local, "claude-haiku-4-5-20251001": cloud,
           "claude-sonnet-5": RecordingProvider("anthropic", "claude-sonnet-5", payload={"label": "OK"})}
    monkeypatch.setattr(ex.ModelRouter, "__init__",
                        lambda self, registry=None: setattr(self, "reg", full_registry))
    monkeypatch.setattr(ex, "_provider_for", lambda mid, prov: reg[mid.split("@")[0]])
    with session_scope() as db:
        r = ex.run_routed(db, agent_type="Research Agent", task_type="reference_analysis",
                          system="s", user="u")
    assert r.error is None and r.fallback_used is True
    assert r.provider == "anthropic" and cloud.calls


def test_local_only_never_calls_cloud_even_on_local_failure(monkeypatch, full_registry):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "allow_cloud_fallback", False)
    dead_local = RecordingProvider("ollama", "gemma3:4b",
                                   raise_error=ProviderError("connection refused"))
    cloud = RecordingProvider("anthropic", "claude-sonnet-5", payload={"x": 1})
    reg = {"gemma3:4b": dead_local, "claude-sonnet-5": cloud, "claude-haiku-4-5-20251001": cloud}
    monkeypatch.setattr(ex.ModelRouter, "__init__",
                        lambda self, registry=None: setattr(self, "reg", full_registry))
    monkeypatch.setattr(ex, "_provider_for", lambda mid, prov: reg[mid.split("@")[0]])
    with session_scope() as db:
        r = ex.run_routed(db, agent_type="Hook Agent", task_type="hook", system="s", user="u")
    assert not cloud.calls                     # cloud never touched
    assert r.error is not None                 # honest failure, not a silent cloud call


def test_telemetry_row_written(wire):
    with session_scope() as db:
        ex.run_routed(db, agent_type="Data Curator", task_type="classification",
                      system="c", user="u", workspace_id="ws1")
    with session_scope() as db:
        ev = db.query(ModelRoutingEvent).filter_by(workspace_id="ws1").first()
        assert ev and ev.model_id == "gemma3:4b" and ev.task_type == "classification"
        assert ev.schema_valid is True and ev.success is True
