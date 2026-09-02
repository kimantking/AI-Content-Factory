"""§AO-§BB / §BR-§BV / §CJ — SNS platform selection: generation skip, generate-only,
all-off + learn-only, queued-job race, re-enable, user override, cost preview."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import session_scope
from app.db.models import Asset, Campaign, PlatformAccount, PlatformContent, PublishJob
from app.intel.platform_selection import (
    cost_preview,
    mode_for,
    platforms_to_generate,
    platforms_to_publish,
    publish_allowed,
    resolve_selection,
    set_selection,
)


@pytest.fixture
def camp(tenant):
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="AI 직업", audience_goal="VIEWS", platforms=[],
                        status="WAITING", workspace_id=tenant["workspace_id"],
                        brand_id=tenant["brand_id"], channel_id=tenant["channel_id"],
                        execution_mode="CREATE_AND_LEARN"))
    return cid


def _content(cid, platform, ct):
    with session_scope() as db:
        db.add(PlatformContent(campaign_id=cid, platform=platform, content_type=ct,
                               title="t", script="s", status="PLANNED", payload={}))


def test_selection_sets_campaign_platforms_to_non_disabled(camp):
    with session_scope() as db:
        res = set_selection(db, campaign_id=camp, selection={
            "youtube_shorts": "GENERATE_AND_PUBLISH",
            "tiktok": {"VIDEO": "GENERATE_AND_PUBLISH"},
            "instagram_reel": "DISABLED",
            "linkedin": {"TEXT": "GENERATE_ONLY"},
        })
    assert set(res["generate_platforms"]) == {"youtube_shorts", "tiktok", "linkedin"}
    assert set(res["publish_platforms"]) == {"youtube_shorts", "tiktok"}
    with session_scope() as db:
        assert set(db.get(Campaign, camp).platforms) == {"youtube_shorts", "tiktok", "linkedin"}
        assert db.get(Campaign, camp).platform_selection_locked is True


def test_generation_skip_no_jobs_for_off_platform(camp):
    from app.publishing.service import create_jobs_for_campaign

    with session_scope() as db:
        set_selection(db, campaign_id=camp, selection={
            "youtube_shorts": "GENERATE_AND_PUBLISH", "tiktok": "DISABLED",
            "instagram_reel": "DISABLED"})
    # content rows may exist for all (e.g. a stale planner) — jobs must still skip
    for p, ct in (("youtube_shorts", "SHORT_VIDEO"), ("tiktok", "VIDEO"), ("instagram_reel", "REELS")):
        _content(camp, p, ct)
    with session_scope() as db:
        jobs = create_jobs_for_campaign(db, camp, run_mode="MANUAL")
        plats = {j.platform for j in jobs}
    assert plats == {"youtube_shorts"}
    with session_scope() as db:
        assert db.query(PublishJob).filter_by(campaign_id=camp, platform="tiktok").count() == 0
        assert db.query(PublishJob).filter_by(campaign_id=camp, platform="instagram_reel").count() == 0


def test_generate_only_makes_content_but_no_job(camp):
    from app.publishing.service import create_jobs_for_campaign

    with session_scope() as db:
        set_selection(db, campaign_id=camp, selection={"linkedin": {"TEXT": "GENERATE_ONLY"}})
    _content(camp, "linkedin", "TEXT")
    with session_scope() as db:
        jobs = create_jobs_for_campaign(db, camp, run_mode="MANUAL")
        assert jobs == []
        assert mode_for(db, camp, "linkedin") == "GENERATE_ONLY"
        assert "linkedin" in platforms_to_generate(db, camp)
        assert "linkedin" not in platforms_to_publish(db, camp)


def test_all_off_selection(camp):
    from app.publishing.service import create_jobs_for_campaign

    with session_scope() as db:
        res = set_selection(db, campaign_id=camp, selection={p: "DISABLED" for p in
                                                            ("youtube_shorts", "tiktok", "x")})
        assert res["generate_platforms"] == []
        assert db.get(Campaign, camp).platforms == []
    _content(camp, "youtube_shorts", "SHORT_VIDEO")
    with session_scope() as db:
        assert create_jobs_for_campaign(db, camp, run_mode="MANUAL") == []


def test_publisher_gate_blocks_deselected_platform_race(camp, tenant):
    """§AY — job queued while TikTok ON, then user turns TikTok OFF, then worker runs."""
    from app.publishing.engine import run_publish_job
    from app.publishing.capabilities import get_capability
    from app.publishing.crypto import encrypt_token

    with session_scope() as db:
        set_selection(db, campaign_id=camp, selection={"youtube_shorts": "GENERATE_AND_PUBLISH",
                                                       "tiktok": "GENERATE_AND_PUBLISH"})
    _content(camp, "tiktok", "VIDEO")
    acc = str(uuid.uuid4())
    with session_scope() as db:
        cap = get_capability("tiktok")
        db.add(PlatformAccount(id=acc, platform="tiktok", account_id="mock-tiktok",
                               account_name="Mock", account_type="BUSINESS",
                               scopes=list(cap.required_scopes),
                               access_token_encrypted=encrypt_token("a"),
                               refresh_token_encrypted=encrypt_token("r"),
                               token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                               connection_status="CONNECTED", integration_status="MOCK_TESTED"))
        job = PublishJob(campaign_id=camp, content_id=db.query(PlatformContent).filter_by(
            campaign_id=camp, platform="tiktok").first().id, platform="tiktok",
            platform_account_id=acc, content_type="VIDEO", status="DRAFT",
            run_mode="FULL_AUTO", approval_status="APPROVED", dry_run=True,
            media_asset_ids=[], platform_selection_mode="GENERATE_AND_PUBLISH")
        db.add(job)
        db.flush()
        jid = job.id
    # user turns TikTok OFF after the job exists
    with session_scope() as db:
        set_selection(db, campaign_id=camp, selection={"youtube_shorts": "GENERATE_AND_PUBLISH",
                                                       "tiktok": "DISABLED"})
    res = run_publish_job(jid)
    assert res["status"] == "BLOCKED"
    assert res["platform_selection"] in ("DISABLED", "GENERATE_ONLY")
    with session_scope() as db:
        j = db.get(PublishJob, jid)
        assert j.last_error_type == "PLATFORM_DESELECTED"
        assert not j.remote_post_id


def test_reenable_reuses_assets_no_duplicate_job(camp):
    from app.publishing.service import create_jobs_for_campaign

    _content(camp, "tiktok", "VIDEO")
    with session_scope() as db:
        set_selection(db, campaign_id=camp, selection={"tiktok": "GENERATE_AND_PUBLISH"})
    with session_scope() as db:
        j1 = create_jobs_for_campaign(db, camp, run_mode="MANUAL")
        j1_ids = [j.id for j in j1]
    assert len(j1_ids) == 1
    with session_scope() as db:
        set_selection(db, campaign_id=camp, selection={"tiktok": "DISABLED"})
    with session_scope() as db:
        assert create_jobs_for_campaign(db, camp, run_mode="MANUAL") == []
    with session_scope() as db:
        set_selection(db, campaign_id=camp, selection={"tiktok": "GENERATE_AND_PUBLISH"})
    with session_scope() as db:
        j2 = create_jobs_for_campaign(db, camp, run_mode="MANUAL")
        j2_ids = [j.id for j in j2]
        total = db.query(PublishJob).filter_by(campaign_id=camp).count()
    assert j2_ids == j1_ids and total == 1            # idempotent, no duplicate


def test_autopilot_cannot_reenable_user_disabled_platform(camp):
    from app.intel.platform_selection import autopilot_may_enable

    with session_scope() as db:
        set_selection(db, campaign_id=camp, selection={"youtube_shorts": "GENERATE_AND_PUBLISH",
                                                       "tiktok": "DISABLED"}, user_explicit=True)
    with session_scope() as db:
        assert autopilot_may_enable(db, campaign_id=camp, platform="tiktok") is False
        assert autopilot_may_enable(db, campaign_id=camp, platform="youtube_shorts") is True


def test_cost_preview_is_honest(camp):
    with session_scope() as db:
        set_selection(db, campaign_id=camp, selection={
            "youtube_shorts": "GENERATE_AND_PUBLISH", "x": {"POST": "GENERATE_AND_PUBLISH"}})
        cp = cost_preview(db, campaign_id=camp)
    assert cp["totals"]["publish_jobs"] == 2
    # media providers are MOCK -> dollar figure is PRICING_UNKNOWN, never fabricated
    assert cp["platforms"]["youtube_shorts"]["est_usd"] == "PRICING_UNKNOWN"
    assert cp["total_est_usd"] == "PRICING_UNKNOWN"
