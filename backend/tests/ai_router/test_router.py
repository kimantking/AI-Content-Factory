"""§18-§22, §26, §27, §80, §81 — Model Router selection logic."""
from __future__ import annotations

import pytest

from app.ai_router.router import ModelRouter


@pytest.fixture
def router(full_registry):
    return ModelRouter(registry=full_registry)


def test_deterministic_tasks_never_call_a_model(router):
    for t in ("hash", "dedup", "similarity", "sort", "numeric", "validation", "cost_calc"):
        d = router.select(agent_type="Fact Checker", task_type=t)
        assert d.deterministic is True
        assert d.selected_model == "python" and d.provider == "python"
        assert d.estimated_cost["usd"] == 0.0


def test_local_light_tasks_prefer_local(router):
    for t in ("classification", "tagging", "url_triage", "topic_clustering", "dataset_cleanup"):
        d = router.select(agent_type="Data Curator", task_type=t)
        assert d.tier == "local_light"
        assert d.selected_model == "gemma3:4b"           # local first
        assert "claude-sonnet-5" in d.fallback_chain      # premium only as a fallback


def test_premium_tasks_pick_a_premium_cloud_model(router):
    for t in ("strategy", "hook", "final_script", "creative_direction"):
        d = router.select(agent_type="Hook Agent", task_type=t)
        assert d.tier == "premium"
        assert d.selected_model == "claude-sonnet-5"      # premium quality class
        assert d.provider == "anthropic"


def test_explicit_ollama_primary_wins_even_for_premium_task(full_registry, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_provider", "ollama")
    d = ModelRouter(registry=full_registry).select(agent_type="Hook Agent", task_type="hook")
    assert d.tier == "premium"
    assert d.selected_model == "gemma3:4b"
    assert d.provider == "ollama"


def test_standard_tasks_use_local_or_cheap_cloud_not_premium_first(router):
    d = router.select(agent_type="Research Agent", task_type="reference_analysis")
    assert d.tier == "standard"
    assert d.selected_model in ("gemma3:4b", "claude-haiku-4-5-20251001")
    assert d.selected_model != "claude-sonnet-5"


def test_not_routed_by_price_only_high_quality_still_not_premium_for_classification(router):
    # even QUALITY_PRESET=max must not send hash/classification to a premium model
    d = router.select(agent_type="Data Curator", task_type="classification", quality_required="max")
    assert d.selected_model != "claude-sonnet-5"
    d2 = router.select(agent_type="Fact Checker", task_type="hash", quality_required="max")
    assert d2.deterministic and d2.selected_model == "python"


def test_fast_preset_softens_premium_to_standard(router):
    d = router.select(agent_type="Hook Agent", task_type="hook", quality_required="fast")
    assert d.tier == "standard"
    assert d.selected_model != "claude-sonnet-5"


def test_complexity_high_bumps_one_tier(router):
    base = router.select(agent_type="Research Agent", task_type="research_summary")
    hi = router.select(agent_type="Research Agent", task_type="research_summary", complexity="high")
    assert base.tier == "standard" and hi.tier == "premium"


def test_budget_pressure_prefers_local(router):
    d = router.select(agent_type="Research Agent", task_type="reference_analysis",
                      budget_state="critical")
    assert d.selected_model == "gemma3:4b"


def test_local_only_removes_cloud_models(full_registry, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "allow_cloud_fallback", False)
    r = ModelRouter(registry=full_registry)
    d = r.select(agent_type="Hook Agent", task_type="hook")   # premium task
    # LOCAL_ONLY: no cloud model is even a candidate -> local, or an honest failure
    assert "claude" not in d.selected_model
    assert d.selected_model in ("gemma3:4b", "")
    assert all("claude" not in m for m in d.fallback_chain)


def test_no_model_available_is_reported_not_crashed(monkeypatch):
    from app.ai_router.registry import ModelEntry, ModelRegistry
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "allow_cloud_fallback", False)
    empty = ModelRegistry([
        ModelEntry("python", "python", "deterministic", "deterministic", enabled=True, health="OK"),
        ModelEntry("gemma3:4b", "ollama", "gemma3", "local", enabled=True, health="DOWN"),
    ])
    d = ModelRouter(registry=empty).select(agent_type="Hook Agent", task_type="hook")
    assert d.selected_model == "" and "no model available" in d.reason
    assert d.estimated_cost["state"] == "UNKNOWN"
