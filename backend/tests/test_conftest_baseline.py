"""Regression guard for the deterministic test baseline.

Root cause of the 2026-09-02 red suite (psycopg DeadlockDetected /
idle-in-transaction termination on model_routing_events) — TEST-ONLY
contamination, two compounding factors:

  1. The real user `.env` set OLLAMA_ENABLED=true and it leaked into the pytest
     runtime. The model router then dispatched standard-tier tasks to the real
     local model (gemma3:4b, ~7s/call), widening every pipeline DB transaction
     window ~100x versus the mock provider.
  2. The suite runs against the SAME Postgres database as the live backend API +
     Celery worker + embedded beat. The autouse `_clean_db` fixture issues
     `TRUNCATE <~90 tables> RESTART IDENTITY CASCADE` before EVERY test, taking
     ACCESS EXCLUSIVE on all of them. Overlap a live query (beat heartbeat,
     publish tick, support-snapshot read) with a wide test transaction and the
     two form a lock cycle -> Postgres kills one.

It is NOT a production transaction race: production never issues TRUNCATE and
never runs a second "test" client; concurrent real campaigns INSERT distinct
serial-PK rows into model_routing_events under a self-compatible RowExclusiveLock,
and recompute_performance locks model_performance rows in deterministic GROUP BY
order. See docs/KNOWN_LIMITATIONS.md.

Fixes:
  * Factor 1 — `tests/conftest.py::_base_settings` forces `ollama_enabled = False`
    (+ `allow_cloud_fallback = True` so routing still resolves, to the mock cloud
    provider). The asserts below fail loudly if a future conftest edit silently
    re-enables real local routing.
  * Factor 2 — operational: run the suite with the live `backend` + `worker`
    containers stopped (Postgres/Redis stay up, no volume loss), or against a
    dedicated test database. Documented in docs/OPERATIONS_RUNBOOK.md.
"""
from __future__ import annotations

from app.ai_router.execute import run_routed
from app.config import get_settings


def test_baseline_disables_real_local_model():
    s = get_settings()
    assert s.ollama_enabled is False, (
        "test baseline must keep Ollama OFF — real local routing makes the suite "
        "slow, non-deterministic, and deadlock-prone against _clean_db TRUNCATE"
    )
    assert s.mock_mode is True
    assert s.llm_provider == "mock"
    assert s.search_provider == "mock"
    # routing must still be able to resolve without a live local model
    assert s.allow_cloud_fallback is True
    # A developer's real .env must not leak into config-capability / support-
    # snapshot assertions (config_check + support_snapshot key off these).
    assert s.app_env == "test"
    assert not s.anthropic_api_key
    assert not s.tavily_api_key
    assert not s.google_api_key
    assert not s.elevenlabs_api_key


def test_standard_tier_routed_call_never_hits_ollama():
    """A standard-tier task under the test baseline must resolve to the mock
    provider, never the ollama provider — proves the deadlock trigger is gone."""
    res = run_routed(
        None, agent_type="Script Agent", task_type="creative_qa_basic",
        system="You are a QA reviewer. Return JSON.",
        user='Review this script. Return {"passed": true, "issues": []}.',
        quality_required="standard",
    )
    assert res.provider != "ollama"
    assert res.model_id != "gemma3:4b"
