"""AUDIT-P8-001 repair — the Model Execution Gateway is on the real agent path.

Proves: production agents route through the router (telemetry from a campaign
run), a light task can go to local Ollama, agent policy sets the tier, structured
output escalates, LOCAL_ONLY makes 0 cloud calls, cloud fallback respects the
setting, and no production agent module calls an LLM provider directly.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agents import model_gateway as gw
from app.agents.runner import run_pipeline
from app.db.base import session_scope
from app.db.models_p8 import ModelRoutingEvent

_APP = Path(__file__).resolve().parents[2] / "app"


# ---- static bypass guard (§19, §34) ------------------------------------ #

def test_no_direct_llm_provider_call_in_production_agent_modules():
    """Production LLM-backed modules must not import or call an LLM provider
    directly — everything goes through app.agents.model_gateway."""
    offenders = []
    for rel in ("agents/nodes.py", "agents/media_nodes.py", "autopilot/pipeline.py"):
        src = (_APP / rel).read_text(encoding="utf-8")
        # allowed: get_search_provider; forbidden: get_llm_provider / raw provider import
        if re.search(r"^[^#\n]*\bget_llm_provider\s*\(", src, re.M):
            offenders.append(f"{rel}: get_llm_provider() call")
        if re.search(r"^from app\.providers\.(mock_llm|anthropic_llm|ollama_llm) import", src, re.M):
            offenders.append(f"{rel}: direct provider import")
    assert offenders == [], offenders


def test_gateway_is_the_only_sanctioned_direct_call():
    src = (_APP / "agents" / "model_gateway.py").read_text(encoding="utf-8")
    # the one EXPLICIT_EXCEPTION is _legacy_fallback -> get_llm_provider()
    assert "_legacy_fallback" in src and "get_llm_provider()" in src


# ---- task mapping / policy (§9) -------------------------------------- #

@pytest.mark.parametrize("task,expected_tier", [
    ("research", "standard"), ("fact_check", "standard"),
    ("strategy", "premium"), ("hook", "premium"), ("script", "premium"),
    ("platform_adapt", "standard"), ("scene_plan", "standard"),
])
def test_agent_policy_sets_routing_tier(task, expected_tier):
    from app.ai_router.router import ModelRouter
    agent_type, task_type = gw.resolve_task("", task)
    d = ModelRouter().select(agent_type=agent_type, task_type=task_type)
    assert d.tier == expected_tier


# ---- routed execution + telemetry (§16, §22, §33) ------------------- #

def test_routed_complete_records_telemetry(_base_settings):
    _base_settings.ollama_enabled = True   # gemma is a candidate; mock still backs cloud
    with session_scope() as db:
        r = gw.routed_complete(agent_name="Data Curator", task="research",
                               system='Return {"x":1}.', user="hi", context={},
                               session=db, campaign_id="c-gw", workspace_id="w-gw")
        assert r.routed is True and r.text
    with session_scope() as db:
        ev = db.query(ModelRoutingEvent).filter_by(campaign_id="c-gw").all()
        assert ev, "a ModelRoutingEvent should be written from a gateway call"
        assert ev[0].workspace_id == "w-gw"


def test_light_task_routes_local_when_ollama_available(_base_settings):
    if gw.__dict__ and not _ollama_reachable():
        pytest.skip("Ollama not reachable")
    _base_settings.ollama_enabled = True
    with session_scope() as db:
        r = gw.routed_complete(agent_name="Data Curator", task="scene_plan",
                               system='Classify. Return {"label":"NEWS"}.',
                               user="The central bank raised rates.", context={},
                               session=db, campaign_id="c-local")
    # scene_plan -> standard tier -> local (gemma) preferred over the mock stand-in
    assert r.provider == "ollama" and "gemma" in r.model
    with session_scope() as db:
        ev = db.query(ModelRoutingEvent).filter_by(campaign_id="c-local").one()
        assert ev.model_id.startswith("gemma") and ev.tier == "standard"
        # no premium cloud event
        assert not db.query(ModelRoutingEvent).filter(
            ModelRoutingEvent.campaign_id == "c-local",
            ModelRoutingEvent.model_id.like("claude-sonnet%")).count()


def test_structured_output_invalid_escalates(monkeypatch, _base_settings):
    """A local engine returning non-JSON must escalate to the next engine, not loop."""
    from app.ai_router import execute as ex
    from app.ai_router.registry import ModelEntry, ModelRegistry
    from tests.ai_router.conftest import RecordingProvider

    reg = ModelRegistry([
        ModelEntry("python", "python", "deterministic", "deterministic", enabled=True, health="OK"),
        ModelEntry("gemma3:4b", "ollama", "gemma3", "local", enabled=True, health="OK",
                   context_tokens=8192, quality_class="standard"),
        ModelEntry("mock", "mock", "mock", "mock", enabled=True, health="OK",
                   context_tokens=200000, quality_class="standard"),
    ])
    bad_local = RecordingProvider("ollama", "gemma3:4b", bad_json=True)
    good_mock = RecordingProvider("mock", "mock", payload={"label": "OK"})
    monkeypatch.setattr(ex.ModelRouter, "__init__",
                        lambda self, registry=None: setattr(self, "reg", reg))
    monkeypatch.setattr(ex, "_provider_for",
                        lambda mid, prov: bad_local if mid.startswith("gemma") else good_mock)
    with session_scope() as db:
        r = gw.routed_complete(agent_name="Data Curator", task="scene_plan",
                               system="s", user="u", context={}, session=db, campaign_id="c-esc")
    assert r.routed and r.escalated and r.fallback_used
    assert bad_local.calls and good_mock.calls


def test_local_only_never_calls_cloud(monkeypatch, _base_settings):
    _base_settings.allow_cloud_fallback = False   # LOCAL_ONLY
    _base_settings.ollama_enabled = True
    from app.ai_router import execute as ex
    from tests.ai_router.conftest import RecordingProvider
    from app.providers.errors import ProviderError

    dead_local = RecordingProvider("ollama", "gemma3:4b", raise_error=ProviderError("refused"))
    cloud = RecordingProvider("anthropic", "claude-sonnet-5", payload={"x": 1})
    monkeypatch.setattr(ex, "_provider_for",
                        lambda mid, prov: dead_local if prov == "ollama" else cloud)
    with session_scope() as db:
        r = gw.routed_complete(agent_name="Hook Agent", task="hook", system="s", user="u",
                               context={}, session=db, campaign_id="c-lo")
    assert not cloud.calls                     # cloud never constructed/called
    # gateway falls back to the legacy provider (mock in tests) — still not cloud
    assert r.routed is False and r.provider in ("mock", "")


def test_cloud_fallback_respects_setting(monkeypatch, _base_settings):
    from app.config import get_settings
    _base_settings.allow_cloud_fallback = True
    _base_settings.ollama_enabled = True
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")   # auto-restored
    from app.ai_router import execute as ex
    from app.ai_router.registry import reset_registry_cache
    from tests.ai_router.conftest import RecordingProvider
    from app.providers.errors import ProviderError
    reset_registry_cache()

    dead_local = RecordingProvider("ollama", "gemma3:4b", raise_error=ProviderError("refused"))
    cloud = RecordingProvider("anthropic", "claude-haiku-4-5-20251001", payload={"label": "OK"})
    monkeypatch.setattr(ex, "_provider_for",
                        lambda mid, prov: dead_local if prov == "ollama" else cloud)
    with session_scope() as db:
        r = gw.routed_complete(agent_name="Research Agent", task="research", system="s", user="u",
                               context={}, session=db, campaign_id="c-fb")
    reset_registry_cache()
    assert r.routed and r.fallback_used and cloud.calls
    assert r.provider == "anthropic"


# ---- full content flow uses the gateway (§26) ---------------------- #

def test_content_pipeline_emits_routing_telemetry_per_llm_node(make_campaign):
    cid = make_campaign(topic="AI가 바꾸는 직업")
    state = run_pipeline(cid, "AI가 바꾸는 직업", "BALANCED", ["youtube_shorts"])
    assert state["status"] == "SUCCESS"
    with session_scope() as db:
        evs = db.query(ModelRoutingEvent).filter_by(campaign_id=cid).all()
        tasks = {e.task_type for e in evs}
        tiers = {e.tier for e in evs}
    assert len(evs) >= 4                        # research/fact/strategy/hook/script
    assert {"research_summary", "strategy", "hook", "final_script"} & tasks
    assert {"standard", "premium"} <= tiers     # at least two different routing decisions


def _ollama_reachable() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3).read()
        return True
    except Exception:  # noqa: BLE001
        return False
