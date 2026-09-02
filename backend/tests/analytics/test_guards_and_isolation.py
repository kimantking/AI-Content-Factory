from __future__ import annotations

import pytest

from app.analytics.base import AnalyticsErrorType, Availability
from app.analytics.faults import analytics_faults
from app.analytics.snapshot import collect_snapshot
from app.db.base import session_scope
from app.db.models import AnalyticsSnapshot, LearningMemory
from app.learning.engine import analyze

pytestmark = pytest.mark.integration


# ---- FALSE DATA: unsupported metric must be null, never 0 ---------------- #

def test_unsupported_metrics_are_null_not_zero(make_published):
    tk = make_published(platform="tiktok", hook="경고", duration=40, ai_video_ratio=0.2,
                        ai_slop=12, publish_hour=19, cta_type="FOLLOW")
    with session_scope() as s:
        snap = collect_snapshot(s, tk["publication_id"], "24h")
        # TikTok API has no watch time / retention / revenue
        assert snap.watch_time_seconds is None
        assert snap.avg_view_percentage is None
        assert snap.estimated_revenue is None
        assert snap.metric_availability.get("watch_time_seconds") == "UNAVAILABLE"
        # views IS supported
        assert snap.views is not None and snap.views > 0

    yt = make_published(platform="youtube_shorts", hook="경고", duration=60, ai_video_ratio=0.1,
                        ai_slop=10, publish_hour=19, cta_type="QUESTION")
    with session_scope() as s:
        ys = collect_snapshot(s, yt["publication_id"], "24h")
        assert ys.estimated_revenue is None                       # not monetized
        assert ys.metric_availability.get("estimated_revenue") == "NOT_AUTHORIZED"


# ---- FALSE LEARNING: one viral outlier != STRONG pattern --------------- #

def test_one_viral_outlier_does_not_create_strong_memory(make_published):
    # 8 weak WARNING-hook shorts + 1 engineered viral outlier
    for _ in range(8):
        make_published(hook="이 직업 사라질 수 있습니다", duration=40, ai_video_ratio=0.5,
                       ai_slop=30, publish_hour=3, cta_type="FOLLOW", scene_var=0.2)
    viral = make_published(hook="이 직업 사라질 수 있습니다", duration=72, ai_video_ratio=0.0,
                           ai_slop=8, publish_hour=19, cta_type="QUESTION", scene_var=1.5)

    with session_scope() as s:
        from app.analytics.performance import compute_performance_score
        from app.db.models import Publication

        for pub in s.query(Publication).all():
            collect_snapshot(s, pub.id, "24h")
        # blow up the outlier so it is flagged
        outlier_pub = [p for p in s.query(Publication)
                       if p.campaign_id == viral["campaign_id"]][0]
        snap = s.query(AnalyticsSnapshot).filter_by(publication_id=outlier_pub.id).first()
        snap.views = (snap.views or 1000) * 200
        s.flush()
        for pub in s.query(Publication).all():
            compute_performance_score(s, pub.id, "BALANCED")

    with session_scope() as s:
        analyze(s)
        hook_mems = s.query(LearningMemory).filter_by(memory_type="HOOK").all()
        # a WARNING-hook memory may exist, but never STRONG off this evidence,
        # and if the win was driven by the single outlier it must be WEAK/EXPERIMENTAL
        for m in hook_mems:
            if m.recommendation.get("value") == "WARNING":
                assert m.status in ("EXPERIMENTAL", "WEAK", "MODERATE")
                assert m.status != "STRONG"


# ---- PLATFORM ISOLATION: one platform's API failure spares others ------ #

def test_platform_analytics_failure_isolation(make_published):
    yt = make_published(platform="youtube_shorts", hook="경고", duration=60, ai_video_ratio=0.1,
                        ai_slop=10, publish_hour=19, cta_type="QUESTION")
    ig = make_published(platform="instagram_reel", hook="경고", duration=40, ai_video_ratio=0.1,
                        ai_slop=10, publish_hour=19, cta_type="SAVE")
    tk = make_published(platform="tiktok", hook="경고", duration=40, ai_video_ratio=0.1,
                        ai_slop=10, publish_hour=19, cta_type="FOLLOW")

    analytics_faults.arm("tiktok", AnalyticsErrorType.RATE_LIMIT, times=99)
    with session_scope() as s:
        tk_status = collect_snapshot(s, tk["publication_id"], "24h").collection_status
        yt_snap = collect_snapshot(s, yt["publication_id"], "24h")
        yt_status, yt_views = yt_snap.collection_status, yt_snap.views
        ig_snap = collect_snapshot(s, ig["publication_id"], "24h")
        ig_status, ig_views = ig_snap.collection_status, ig_snap.views

    assert tk_status == "FAILED"                                    # tiktok failed
    assert yt_status in ("SUCCESS", "PARTIAL") and yt_views         # youtube fine
    assert ig_status in ("SUCCESS", "PARTIAL") and ig_views         # instagram fine
