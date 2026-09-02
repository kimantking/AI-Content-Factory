from __future__ import annotations

import uuid

import pytest

from app.db.base import session_scope
from app.db.models import (
    Campaign,
    ContentFeature,
    PerformanceScore,
    RevenueEntry,
)


@pytest.fixture(autouse=True)
def _reset_trend_faults():
    from app.trends.faults import trend_faults

    trend_faults.clear()
    yield
    trend_faults.clear()


_AP_KEYS = [
    "trend_client", "opportunity_formula_version", "autopilot_mode", "autopilot_objective",
    "autopilot_stage1_keep", "autopilot_stage2_keep", "autopilot_daily_content_min",
    "autopilot_daily_content_max", "autopilot_daily_budget_usd", "autopilot_monthly_budget_usd",
    "autopilot_daily_hard_budget_usd", "autopilot_monthly_hard_budget_usd",
    "autopilot_daily_post_limit", "autopilot_emergency_stop", "autopilot_blocked_topics",
    "autopilot_blocked_keywords", "autopilot_min_opportunity_score", "autopilot_trend_reserve_ratio",
    "autopilot_exploration_ratio", "autopilot_max_risk_level", "autopilot_platform_opportunity_threshold",
    "autopilot_publish_all_platforms", "autopilot_config_version", "autopilot_respect_channel_capacity",
]


@pytest.fixture(autouse=True)
def _autopilot_defaults(_base_settings):
    s = _base_settings
    saved = {k: getattr(s, k) for k in _AP_KEYS}
    s.trend_client = "mock"
    s.autopilot_mode = "SHADOW"
    s.autopilot_stage1_keep = 14
    s.autopilot_stage2_keep = 6
    s.autopilot_daily_content_min = 1
    s.autopilot_daily_content_max = 3
    s.autopilot_daily_budget_usd = 3.0
    s.autopilot_daily_hard_budget_usd = 6.0
    s.autopilot_emergency_stop = False
    s.autopilot_blocked_topics = []
    s.autopilot_blocked_keywords = []
    s.run_inline = True
    s.dry_run = True
    yield s
    for k, v in saved.items():
        setattr(s, k, v)


def _seed_history(topic: str, *, cluster: str, score: float, rel: float,
                  revenue: float = 0.0, n: int = 3) -> None:
    """A few ContentFeature + PerformanceScore rows so historical/audience/revenue
    sub-scores can discriminate."""
    from app.analytics.embedding import embed

    with session_scope() as s:
        for i in range(n):
            cid = str(uuid.uuid4())
            content_id = str(uuid.uuid4())
            s.add(Campaign(id=cid, topic=topic, platforms=["youtube_shorts"], status="SUCCESS"))
            s.flush()
            s.add(ContentFeature(content_id=content_id, campaign_id=cid, platform="youtube_shorts",
                                 content_type="SHORT_VIDEO", topic=topic, topic_cluster=cluster,
                                 topic_embedding=embed(topic), hook_type="WARNING",
                                 cta_type="QUESTION", video_duration=70.0, scene_count=5,
                                 ai_slop_score=10.0))
            s.add(PerformanceScore(publication_id=str(uuid.uuid4()), content_id=content_id,
                                   campaign_id=cid, platform="youtube_shorts",
                                   content_type="SHORT_VIDEO", objective="BALANCED",
                                   score=score, relative_score=rel))
            if revenue:
                s.add(RevenueEntry(campaign_id=cid, content_id=content_id, source="SPONSOR",
                                   amount=revenue, is_estimate=False))


@pytest.fixture
def seed_history():
    return _seed_history
