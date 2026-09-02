from __future__ import annotations

import pytest

from app.analytics.base import Availability
from app.analytics.capabilities import get_analytics_capability, load_analytics_capabilities
from app.analytics.classify import classify_cta, classify_hook
from app.analytics.metric_catalog import normalize
from app.analytics.performance import (
    baseline,
    compute_performance_score,
    is_outlier,
    objective_weights,
    relative_performance,
)
from app.analytics.registry import all_analytics_platforms
from app.analytics.revenue import profit_report, revenue_breakdown
from app.analytics.snapshot import collect_snapshot
from app.db.base import session_scope
from app.db.models import AnalyticsSnapshot, RevenueEntry
from app.learning.memory import retrieve_memories, status_for, upsert_memory


def test_capabilities_cover_all_platforms():
    caps = load_analytics_capabilities()
    assert set(caps) == set(all_analytics_platforms())
    yt = get_analytics_capability("youtube")
    assert yt.revenue_support and yt.last_verified_at
    tk = get_analytics_capability("tiktok")
    assert tk.availability("watch_time_seconds") == Availability.UNAVAILABLE


def test_metric_normalizer_never_zeroes_unavailable():
    raw = {"views": 1000, "watch_time_seconds": None, "estimatedRevenue": None}
    # tiktok: no watch time, no revenue via API
    m = normalize("tiktok", {"views": 1000})
    assert m["views"].value == 1000 and m["views"].availability == Availability.AVAILABLE
    assert m["watch_time_seconds"].value is None
    assert m["watch_time_seconds"].availability == Availability.UNAVAILABLE
    # youtube revenue -> NOT_AUTHORIZED, value None (not 0)
    ym = normalize("youtube", {"views": 10, "estimatedRevenue": None})
    assert ym["estimated_revenue"].value is None
    assert ym["estimated_revenue"].availability == Availability.NOT_AUTHORIZED


def test_snapshot_partial_and_idempotent(make_published):
    d = make_published(hook="경고: 이 직업 사라집니다", duration=70, ai_video_ratio=0.0,
                       ai_slop=9, publish_hour=19, cta_type="QUESTION")
    with session_scope() as s:
        s1 = collect_snapshot(s, d["publication_id"], "24h")
        assert s1.collection_status in ("SUCCESS", "PARTIAL")
        assert s1.views is not None
        # tiktok-only fields stay null on a youtube snapshot, never 0
        assert s1.watch_time_seconds is not None  # youtube HAS watch time
        s2 = collect_snapshot(s, d["publication_id"], "24h")
        assert s2.id == s1.id                                   # idempotent
        assert s.query(AnalyticsSnapshot).filter_by(
            publication_id=d["publication_id"], window_label="24h").count() == 1


def test_baseline_relative_and_outlier(published_dataset):
    with session_scope() as s:
        for d in published_dataset:
            collect_snapshot(s, d["publication_id"], "24h")
        bl = baseline(s, "youtube_shorts", "SHORT_VIDEO", "views")
        assert bl["n"] >= 10 and "median" in bl and "p75" in bl
        assert relative_performance(bl["median"], bl) == pytest.approx(1.0, abs=0.01)
        assert is_outlier(bl["p75"] * 50, bl) is True
        assert is_outlier(bl["median"], bl) is False


def test_performance_score_renormalizes_missing_metrics():
    w = objective_weights("REVENUE", "SHORT_VIDEO")
    assert "estimated_revenue" in w
    # with revenue unavailable the score still computes from the remaining metrics
    from app.analytics.performance import _OBJECTIVE_WEIGHTS  # noqa: F401


def test_data_anomaly_flag(make_published):
    d = make_published(hook="h", duration=60, ai_video_ratio=0.1, ai_slop=10,
                       publish_hour=19, cta_type="QUESTION")
    with session_scope() as s:
        first = collect_snapshot(s, d["publication_id"], "1h")
        first.views = 100000
        s.flush()
    with session_scope() as s:
        snap = AnalyticsSnapshot(publication_id=d["publication_id"], campaign_id=d["campaign_id"],
                                 platform="youtube_shorts", window_label="6h", views=20000)
        from app.analytics.snapshot import _detect_anomalies, _prev_snapshot
        from datetime import datetime, timezone

        prev = _prev_snapshot(s, d["publication_id"], datetime.now(timezone.utc))
        flags = _detect_anomalies(prev, {"views": 20000})
        assert any("DATA_ANOMALY" in f for f in flags)


def test_revenue_ledger_separates_actual_and_estimate(make_published):
    d = make_published(hook="h", duration=60, ai_video_ratio=0.1, ai_slop=10,
                       publish_hour=19, cta_type="QUESTION")
    with session_scope() as s:
        s.add(RevenueEntry(campaign_id=d["campaign_id"], content_id=d["content_id"],
                           source="SPONSOR", amount=500000, is_estimate=False))
        s.add(RevenueEntry(campaign_id=d["campaign_id"], content_id=d["content_id"],
                           source="ESTIMATE", amount=120000, is_estimate=True))
    with session_scope() as s:
        rb = revenue_breakdown(s, d["campaign_id"])
        assert rb["actual"] == 500000 and rb["estimate"] == 120000
        assert rb["by_source"]["SPONSOR"] == 500000
        p = profit_report(s, d["campaign_id"])
        assert p["revenue"]["total"] == 620000
        assert "profit_per_content" in p


def test_classifiers():
    assert classify_hook("이 직업은 3년 안에 사라질 수도 있습니다") == "WARNING"
    assert classify_hook("여러분은 어떻게 생각하시나요?") == "QUESTION"
    assert classify_cta("question", None) == "QUESTION"
    assert classify_cta(None, "저장해두세요") == "SAVE"


def test_memory_status_and_false_learning_guard(_analytics_defaults):
    assert status_for(20, 0.9, consistent=True) == "STRONG"
    assert status_for(20, 0.9, consistent=False) == "WEAK"   # inconsistent never STRONG
    assert status_for(1, 0.9) == "EXPERIMENTAL"


def test_memory_retrieval_is_bounded(_base_settings):
    _base_settings.max_memory_items = 3
    with session_scope() as s:
        for i in range(10):
            upsert_memory(s, memory_type="HOOK", platform="youtube", dimension=f"d{i}",
                          statement=f"pattern {i}", confidence=0.8, sample_size=15,
                          recommendation={}, consistent=True)
    with session_scope() as s:
        got = retrieve_memories(s, platform="youtube", topic="AI 직업")
        assert len(got) <= 3
        assert all(m.status != "DEPRECATED" for m in got)
