"""§34-§46, §84-§86 — Content Library: discovery of EXISTING content, legacy
compatibility, video preview, add-platform-later."""
from __future__ import annotations

import uuid

import pytest

from app.db.base import session_scope
from app.db.models import (
    Asset,
    Campaign,
    PlatformContent,
    Publication,
    PublishJob,
    RevenueEntry,
    Script,
)
from app.library import add_platform_to_campaign, content_detail, library_stats, list_content


@pytest.fixture
def legacy_campaign(tmp_path):
    """A pre-Governance, pre-tenant campaign with a real MP4 render + a publication."""
    cid = str(uuid.uuid4())
    mp4 = tmp_path / "old_render.mp4"
    mp4.write_bytes(b"\x00" * 120_000)
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="예전에 만든 번역 영상", audience_goal="VIEWS",
                        platforms=["youtube_shorts"], status="SUCCESS"))   # no workspace_id / execution_mode
        db.add(Script(campaign_id=cid, platform="MASTER", body="옛날 대본 본문입니다. " * 20,
                      word_count=60, qa_passed=True, qa_report={}, ai_slop_score=15.0, naturalness={}))
        c = PlatformContent(campaign_id=cid, platform="youtube_shorts", content_type="SHORT_VIDEO",
                            hook="번역가는 사라질까", title="AI 번역의 미래", caption="", script="본문",
                            status="PUBLISHED", payload={})
        db.add(c)
        db.flush()
        db.add(Asset(campaign_id=cid, content_id=c.id, asset_type="render", provider="ffmpeg",
                     provider_mode="REAL", storage_path=str(mp4), mime_type="video/mp4",
                     width=1080, height=1920, duration=31.0, status="SUCCESS",
                     meta={"fps": 30, "version": 1}))
        db.add(Asset(campaign_id=cid, content_id=c.id, asset_type="thumbnail", provider="pil",
                     provider_mode="REAL", storage_path=str(tmp_path / "thumb.png"),
                     mime_type="image/png", status="SUCCESS", meta={}))
        job = PublishJob(campaign_id=cid, content_id=c.id, platform="youtube_shorts",
                         content_type="SHORT_VIDEO", status="PUBLISHED", run_mode="MANUAL")
        db.add(job)
        db.flush()
        db.add(Publication(publish_job_id=job.id, campaign_id=cid, content_id=c.id,
                           platform="youtube_shorts", status="PUBLISHED",
                           remote_url="https://youtube.com/shorts/xyz"))
        db.add(RevenueEntry(campaign_id=cid, content_id=c.id, source="PLATFORM_API",
                            amount=12000, currency="KRW", is_estimate=False))
    return cid


def test_existing_content_is_discovered(legacy_campaign):
    with session_scope() as db:
        res = list_content(db)
    ids = {c["campaign_id"] for c in res["items"]}
    assert legacy_campaign in ids
    card = next(c for c in res["items"] if c["campaign_id"] == legacy_campaign)
    assert card["legacy"] is True
    assert card["has_video"] is True and card["video_playable"] is True
    assert card["publish_state"] == "PUBLISHED"
    assert card["platforms"] == ["youtube_shorts"]
    assert card["revenue_actual"] == 12000.0


def test_legacy_detail_does_not_crash_and_marks_not_applicable(legacy_campaign):
    with session_scope() as db:
        d = content_detail(db, legacy_campaign)
    assert d["overview"]["legacy"] is True
    assert d["overview"]["governance"] == "NOT_APPLICABLE"
    assert d["preview"]["video_playable"] is True and d["preview"]["size_bytes"] == 120_000
    assert d["script"]["master"]["word_count"] == 60
    assert d["publishing"][0]["remote_url"].startswith("https://youtube.com")
    assert d["history"]                          # script + asset versions present


def test_stats_counts_legacy(legacy_campaign):
    with session_scope() as db:
        s = library_stats(db)
    assert s["total_campaigns"] >= 1
    assert s["legacy_campaigns"] >= 1
    assert s["campaigns_with_video"] >= 1
    assert s["published_campaigns"] >= 1


def test_search_and_filter(legacy_campaign):
    with session_scope() as db:
        by_topic = list_content(db, query="번역")
        by_script = list_content(db, query="옛날 대본")
        wrong_platform = list_content(db, platform="tiktok")
    assert any(c["campaign_id"] == legacy_campaign for c in by_topic["items"])
    assert any(c["campaign_id"] == legacy_campaign for c in by_script["items"])
    assert all(c["campaign_id"] != legacy_campaign for c in wrong_platform["items"])


def test_pagination(tmp_path):
    with session_scope() as db:
        for i in range(7):
            db.add(Campaign(id=str(uuid.uuid4()), topic=f"페이지 테스트 {i}", audience_goal="VIEWS",
                            platforms=[], status="WAITING"))
    with session_scope() as db:
        p1 = list_content(db, page=1, page_size=3)
        p2 = list_content(db, page=2, page_size=3)
    assert p1["page_size"] == 3 and len(p1["items"]) == 3
    assert p1["total"] >= 7 and p1["pages"] >= 3
    assert {c["campaign_id"] for c in p1["items"]}.isdisjoint({c["campaign_id"] for c in p2["items"]})


def test_add_platform_later_only_adds_new(legacy_campaign):
    with session_scope() as db:
        res = add_platform_to_campaign(db, campaign_id=legacy_campaign, platform="instagram_reel")
        assert res["ok"] and res["added"] == "instagram_reel"
        assert res["generate_now"] == ["instagram_reel"]
        assert "youtube_shorts" in res["unchanged"]
        camp = db.get(Campaign, legacy_campaign)
        assert set(camp.platforms) == {"youtube_shorts", "instagram_reel"}
        # existing youtube content untouched
        yt = db.query(PlatformContent).filter_by(campaign_id=legacy_campaign, platform="youtube_shorts").count()
        assert yt == 1
        ig = db.query(PlatformContent).filter_by(campaign_id=legacy_campaign, platform="instagram_reel").count()
        assert ig == 0    # not generated yet — pipeline builds it, not this call


def test_add_existing_platform_is_rejected(legacy_campaign):
    with session_scope() as db:
        res = add_platform_to_campaign(db, campaign_id=legacy_campaign, platform="youtube_shorts")
    assert res["ok"] is False and "already generated" in res["error"]


def test_demo_video_flagged_not_production(tmp_path):
    cid = str(uuid.uuid4())
    demo = tmp_path / "advanced_short.mp4"
    demo.write_bytes(b"\x00" * 5000)
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="데모", audience_goal="VIEWS", platforms=[], status="SUCCESS"))
        db.flush()
        db.add(Asset(campaign_id=cid, asset_type="render", provider="ffmpeg", provider_mode="REAL",
                     storage_path=str(demo), mime_type="video/mp4", duration=8.0, status="SUCCESS", meta={}))
    with session_scope() as db:
        card = next(c for c in list_content(db)["items"] if c["campaign_id"] == cid)
        assert card["is_demo"] is True
