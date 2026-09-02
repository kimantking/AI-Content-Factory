from __future__ import annotations

import uuid

import pytest

from app.analytics.performance import compute_performance_score
from app.analytics.snapshot import collect_snapshot
from app.db.base import session_scope
from app.db.models import (
    AnalyticsSnapshot,
    Campaign,
    ContentRecipe,
    LearningMemory,
    LearningRun,
    Publication,
)
from app.learning.reports import daily_learning_run

pytestmark = pytest.mark.integration


def test_snapshot_and_daily_learning_are_idempotent(published_dataset):
    with session_scope() as s:
        for d in published_dataset:
            collect_snapshot(s, d["publication_id"], "24h")
            compute_performance_score(s, d["publication_id"], "BALANCED")

    with session_scope() as s:
        run1 = daily_learning_run(s, "2026-08-31")
        run1_date = run1.run_date
        run1_id = run1.id
        n_snap_1 = s.query(AnalyticsSnapshot).count()

    # "worker restart" -> re-run the same collection + same daily job
    with session_scope() as s:
        for d in published_dataset:
            collect_snapshot(s, d["publication_id"], "24h")   # no dup snapshot
        run2 = daily_learning_run(s, "2026-08-31")            # same run_date row
        run2_date, run2_id = run2.run_date, run2.id

    with session_scope() as s:
        assert s.query(AnalyticsSnapshot).count() == n_snap_1
        assert s.query(LearningRun).filter_by(run_date="2026-08-31").count() == 1
    assert run1_date == run2_date == "2026-08-31"
    assert run1_id == run2_id                                 # same row updated, not a new one


def test_end_to_end_learning_loop_and_memory_injection(published_dataset):
    # 1) collect analytics for ~20 published contents + score them
    with session_scope() as s:
        for d in published_dataset:
            snap = collect_snapshot(s, d["publication_id"], "24h")
            assert snap.collection_status in ("SUCCESS", "PARTIAL")
            compute_performance_score(s, d["publication_id"], "BALANCED")

    # 2) run the daily learning job -> memories + recipes
    with session_scope() as s:
        run = daily_learning_run(s)
        assert run.summary["records"] >= 15

    with session_scope() as s:
        mems = s.query(LearningMemory).all()
        assert mems, "learning produced no memories"
        # the engineered signal: WARNING hooks / 60-85s / low slop / evening should
        # surface as a non-experimental pattern somewhere
        strong_ish = [m for m in mems if m.status in ("MODERATE", "STRONG")]
        assert strong_ish, "no MODERATE/STRONG memory despite an engineered signal"
        assert all(m.sample_size >= 3 and m.evidence_ids is not None for m in strong_ish)
        # every recommendation carries evidence + sample size + confidence
        for m in strong_ish:
            assert m.confidence > 0 and m.sample_size > 0

        recipes = s.query(ContentRecipe).all()
        assert recipes, "no content recipe assembled"

    # 3) a NEW campaign's Strategy step receives that memory as STRATEGIC GUIDANCE
    from app.learning.injection import strategy_memory_context

    with session_scope() as s:
        ctx = strategy_memory_context(s, topic="인공지능이 대체할 일자리",
                                      platforms=["youtube_shorts"], objective="BALANCED")
    assert ctx["enabled"] is True
    assert ctx["items"], "no memory injected into strategy context"
    assert "STRATEGIC GUIDANCE" in ctx["text"]
    assert "correlation" in ctx["text"].lower()   # not presented as fact


def test_memory_injection_reaches_strategy_node(published_dataset, _base_settings):
    # build memories first
    with session_scope() as s:
        for d in published_dataset:
            collect_snapshot(s, d["publication_id"], "24h")
            compute_performance_score(s, d["publication_id"], "BALANCED")
        daily_learning_run(s)

    from app.agents.runner import run_pipeline

    cid = str(uuid.uuid4())
    topic = "인공지능이 대체할 일자리"
    with session_scope() as s:
        s.add(Campaign(id=cid, topic=topic, audience_goal="BALANCED",
                       platforms=["youtube_shorts"], status="WAITING"))
    state = run_pipeline(cid, topic, "BALANCED", ["youtube_shorts"])
    assert state["status"] == "SUCCESS"
    mc = state["strategy"].get("_memory_context", {})
    assert mc.get("enabled") is True
    assert mc.get("items"), "strategy_node did not receive injected memories"
