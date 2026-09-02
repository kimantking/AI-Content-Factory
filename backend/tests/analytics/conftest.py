from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import session_scope
from app.db.models import (
    Campaign,
    PlatformContent,
    Publication,
    PublishJob,
    Scene,
    Script,
)


@pytest.fixture(autouse=True)
def _reset_analytics_faults():
    from app.analytics.faults import analytics_faults

    analytics_faults.clear()
    yield
    analytics_faults.clear()


@pytest.fixture(autouse=True)
def _analytics_defaults(_base_settings):
    _base_settings.analytics_client = "mock"
    _base_settings.default_objective = "BALANCED"
    _base_settings.memory_min_moderate_sample = 5
    _base_settings.memory_min_strong_sample = 9
    yield


def _make_published(
    *, platform: str = "youtube_shorts", hook: str, duration: float,
    ai_video_ratio: float, ai_slop: float, publish_hour: int, cta_type: str,
    scene_var: float = 1.2, published_days_ago: int = 3, campaign_status: str = "SUCCESS",
    seed_tag: str | None = None,
) -> dict:
    """Insert a minimal PUBLISHED content tree with the given feature knobs."""
    cid = str(uuid.uuid4())
    content_id = str(uuid.uuid4())
    pub_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    published_at = datetime.now(timezone.utc) - timedelta(days=published_days_ago)
    n_scenes = 5
    with session_scope() as s:
        s.add(Campaign(id=cid, topic="AI로 사라질 가능성이 높은 직업", audience_goal="BALANCED",
                       platforms=[platform], status=campaign_status,
                       knowledge_pack={"topic": "AI로 사라질 가능성이 높은 직업"}))
        s.flush()
        s.add(PlatformContent(id=content_id, campaign_id=cid, platform=platform,
                              content_type="SHORT_VIDEO", hook=hook, script="본문 " * 40,
                              title="AI 직업", caption="cap", cta="댓글로 알려주세요",
                              hashtags=["#AI"], payload={"cta_type": cta_type}, status="SUCCESS"))
        s.add(Script(campaign_id=cid, platform="MASTER", body="스크립트 " * 60, word_count=60,
                     qa_passed=True, naturalness={"ai_slop_after": ai_slop, "ai_slop_before": ai_slop + 5}))
        s.add(PublishJob(id=job_id, campaign_id=cid, content_id=content_id,
                         platform=platform, content_type="SHORT_VIDEO", status="PUBLISHED",
                         idempotency_key=str(uuid.uuid4()), title="AI 직업",
                         scheduled_at=published_at.replace(hour=publish_hour, minute=0),
                         published_at=published_at.replace(hour=publish_hour, minute=0)))
        s.flush()
        # scenes: force durations to hit the requested variance + total duration
        per = duration / n_scenes
        for i in range(n_scenes):
            d = per * (1.6 if (i % 2 == 0 and scene_var > 1.0) else 0.5) if scene_var > 1.0 else per
            vt = "AI_VIDEO" if i < round(n_scenes * ai_video_ratio) else "AI_IMAGE"
            s.add(Scene(campaign_id=cid, content_id=content_id, scene_order=i,
                        estimated_duration=round(max(0.8, d), 2), visual_type=vt,
                        camera_motion=["SLOW_ZOOM_IN", "PAN_LEFT", "KEN_BURNS", "PAN_UP", "SLOW_ZOOM_OUT"][i],
                        highlight_words=["20%"] if i == 2 else []))
        s.flush()
        rp = f"rp_{seed_tag}" if seed_tag else f"rp_{pub_id[:8]}"
        s.add(Publication(id=pub_id, publish_job_id=job_id, campaign_id=cid,
                          content_id=content_id, platform=platform, status="PUBLISHED",
                          remote_post_id=rp,
                          remote_url=f"https://mock/{rp}",
                          published_at=published_at.replace(hour=publish_hour, minute=0),
                          provider_mode="MOCK"))
    return {"campaign_id": cid, "content_id": content_id, "publication_id": pub_id}


@pytest.fixture
def make_published():
    return _make_published


@pytest.fixture
def published_dataset(_analytics_defaults):
    """~20 published shorts: WARNING hooks + 60-85s + low slop are engineered to
    outperform (via the mock provider's baked-in signal)."""
    rows = []
    for i in range(20):
        winner = i % 2 == 0
        rows.append(_make_published(
            hook=("이 직업, 3년 안에 사라질 수도 있습니다." if winner
                  else "오늘은 인공지능에 대해 알아보겠습니다."),
            duration=(72.0 if winner else 33.0),
            ai_video_ratio=(0.0 if winner else 0.6),
            ai_slop=(8.0 if winner else 28.0),
            publish_hour=(19 if winner else 3),
            cta_type=("QUESTION" if winner else "FOLLOW"),
            scene_var=(1.4 if winner else 0.2),
            published_days_ago=30 - i,
            seed_tag=f"{'win' if winner else 'lose'}{i:02d}",   # deterministic mock metrics
        ))
    return rows
