"""§32, §33 — routing telemetry + model performance memory (min-sample guard)."""
from __future__ import annotations

from app.ai_router.telemetry import performance_hint, recompute_performance, record_event
from app.db.base import session_scope
from app.db.models_p8 import ModelPerformance


def _seed(db, model, task, n, *, schema_valid=True, success=True, quality=0.9):
    for _ in range(n):
        record_event(db, agent_type="Data Curator", task_type=task, tier="local_light",
                     model_id=model, provider="ollama", latency_ms=800, input_tokens=100,
                     output_tokens=40, schema_valid=schema_valid, success=success,
                     quality_signal=quality)


def test_recompute_builds_per_model_task_rows():
    with session_scope() as db:
        _seed(db, "gemma3:4b", "classification", 12, quality=0.95)
        _seed(db, "gemma3:4b", "hook", 12, schema_valid=True, success=False, quality=0.2)
        recompute_performance(db)
    with session_scope() as db:
        strong = db.query(ModelPerformance).filter_by(model_id="gemma3:4b", task_type="classification").one()
        weak = db.query(ModelPerformance).filter_by(model_id="gemma3:4b", task_type="hook").one()
        assert strong.strength == "STRONG" and strong.sample_size == 12
        assert weak.strength == "WEAK"


def test_min_sample_guard_keeps_strength_unknown():
    with session_scope() as db:
        _seed(db, "gemma3:4b", "url_triage", 3, quality=0.99)   # below model_routing_min_sample
        recompute_performance(db)
        row = db.query(ModelPerformance).filter_by(model_id="gemma3:4b", task_type="url_triage").one()
        assert row.strength == "UNKNOWN"
        hint = performance_hint(db, task_type="url_triage")
        assert "gemma3:4b" not in hint      # not enough data to influence routing


def test_performance_hint_exposes_strong_and_weak_when_sampled():
    with session_scope() as db:
        _seed(db, "gemma3:4b", "classification", 20, quality=0.97)
        _seed(db, "claude-haiku-4-5-20251001", "classification", 20, quality=0.98)
        recompute_performance(db)
        hint = performance_hint(db, task_type="classification")
    assert hint.get("gemma3:4b") in ("STRONG", "OK")
