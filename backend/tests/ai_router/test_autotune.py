"""AUDIT-P8-005 — once telemetry has >= min_sample obs, ModelRouter.select()
prefers a proven-STRONG engine and pushes a proven-WEAK one down. Below the
floor, or with the switch off, routing is unchanged.
"""
from __future__ import annotations

from app.ai_router.router import ModelRouter
from app.ai_router.telemetry import recompute_performance, record_event
from app.db.base import session_scope


def _seed(db, model, task, n, *, schema_valid, success, quality):
    for _ in range(n):
        record_event(db, agent_type="Research Agent", task_type=task, tier="standard",
                     model_id=model, provider="ollama" if model.startswith("gemma") else "anthropic",
                     latency_ms=700, input_tokens=100, output_tokens=40,
                     schema_valid=schema_valid, success=success, quality_signal=quality)


def test_weak_engine_is_downranked_after_enough_samples(full_registry, _base_settings):
    task = "research_summary"
    with session_scope() as db:
        # gemma proven WEAK, haiku proven STRONG on this task
        _seed(db, "gemma3:4b", task, 12, schema_valid=False, success=False, quality=0.15)
        _seed(db, "claude-haiku-4-5-20251001", task, 12, schema_valid=True, success=True, quality=0.97)
        recompute_performance(db)

        base = ModelRouter(full_registry).select(agent_type="Research Agent", task_type=task)
        tuned = ModelRouter(full_registry).select(agent_type="Research Agent", task_type=task, db=db)

    assert base.selected_model == "gemma3:4b"                 # standard tier -> local first
    assert tuned.selected_model == "claude-haiku-4-5-20251001"  # WEAK local pushed below STRONG
    assert "gemma3:4b" in tuned.fallback_chain                # still available as fallback


def test_no_shift_below_min_sample(full_registry, _base_settings):
    task = "research_summary"
    with session_scope() as db:
        _seed(db, "gemma3:4b", task, 3, schema_valid=False, success=False, quality=0.1)
        recompute_performance(db)
        tuned = ModelRouter(full_registry).select(agent_type="Research Agent", task_type=task, db=db)
    assert tuned.selected_model == "gemma3:4b"                # 3 < min_sample -> ignored


def test_autotune_switch_off_keeps_default(full_registry, _base_settings):
    _base_settings.model_routing_autotune_enabled = False
    task = "research_summary"
    with session_scope() as db:
        _seed(db, "gemma3:4b", task, 12, schema_valid=False, success=False, quality=0.1)
        _seed(db, "claude-haiku-4-5-20251001", task, 12, schema_valid=True, success=True, quality=0.99)
        recompute_performance(db)
        tuned = ModelRouter(full_registry).select(agent_type="Research Agent", task_type=task, db=db)
    assert tuned.selected_model == "gemma3:4b"
