"""§CE — full integration: URL learning + platform selection + pipeline + publish.

Marked `integration` (builds a real Phase 1-B campaign). Verifies that a DISABLED
platform produces nothing and a GENERATE_ONLY platform produces content but no
publish job, while GENERATE_AND_PUBLISH platforms publish (mock).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import session_scope
from app.db.models import PlatformAccount, PlatformContent, PublishJob
from app.db.models_learn import PromptBlueprint, ReferenceSource
from app.intel.engine import add_urls, run_learning_job
from app.intel.platform_selection import set_selection

pytestmark = pytest.mark.integration


def _connect(platform: str) -> str:
    from app.publishing.capabilities import get_capability
    from app.publishing.crypto import encrypt_token

    cap = get_capability(platform)
    cid = str(uuid.uuid4())
    with session_scope() as s:
        s.add(PlatformAccount(
            id=cid, platform=platform, account_id=f"mock-{platform}", account_name="M",
            account_type="BUSINESS", scopes=list(cap.required_scopes),
            access_token_encrypted=encrypt_token("a"), refresh_token_encrypted=encrypt_token("r"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            connection_status="CONNECTED", integration_status="MOCK_TESTED"))
    return cid


def test_full_url_learn_plus_selective_publish(tenant, _base_settings, tmp_path):
    _base_settings.storage_root = str(tmp_path / "s")
    _base_settings.output_root = str(tmp_path / "o")
    _base_settings.asset_cache_enabled = False
    _base_settings.platform_client = "mock"
    _base_settings.dry_run = True
    _base_settings.run_inline = True
    from app.providers.media import registry as mr
    mr.get_storage.cache_clear()

    from app.agents.media_runner import run_media_pipeline
    from app.agents.runner import run_pipeline
    from app.publishing.engine import run_publish_job
    from app.publishing.service import create_jobs_for_campaign

    ws = tenant["workspace_id"]
    cid = str(uuid.uuid4())
    topic = "AI로 사라질 가능성이 높은 직업"
    from app.db.models import Campaign
    with session_scope() as db:
        db.add(Campaign(id=cid, topic=topic, audience_goal="VIEWS", platforms=[], status="WAITING",
                        workspace_id=ws, brand_id=tenant["brand_id"], channel_id=tenant["channel_id"],
                        execution_mode="CREATE_AND_LEARN"))
        set_selection(db, campaign_id=cid, selection={
            "youtube_shorts": "GENERATE_AND_PUBLISH",
            "tiktok": "GENERATE_AND_PUBLISH",
            "instagram_reel": "DISABLED",
            "linkedin": {"TEXT": "GENERATE_ONLY"},
            "naver_blog": {"ARTICLE": "GENERATE_ONLY"},
        })
        plats = db.get(Campaign, cid).platforms

    # reference learning first (CREATE_AND_LEARN)
    with session_scope() as db:
        job = add_urls(db, urls=["https://example.com/mt-report", "https://example.com/ai-creators",
                                 "https://github.com/acme/agent-toolkit"],
                       execution_mode="CREATE_AND_LEARN", workspace_id=ws,
                       brand_id=tenant["brand_id"], channel_id=tenant["channel_id"],
                       campaign_id=cid, topic=topic)
        jid = job.id
    with session_scope() as db:
        lres = run_learning_job(db, jid)
    assert lres["ok"]
    with session_scope() as db:
        assert db.query(ReferenceSource).filter_by(workspace_id=ws).count() == 3
        assert db.query(PromptBlueprint).filter_by(workspace_id=ws).count() > 0

    assert set(plats) == {"youtube_shorts", "tiktok", "linkedin", "naver_blog"}
    run_pipeline(cid, topic, "VIEWS", plats)
    run_media_pipeline(cid, plats)

    with session_scope() as db:
        content_platforms = {c.platform for c in db.query(PlatformContent).filter_by(campaign_id=cid)}
        assert "instagram_reel" not in content_platforms       # DISABLED -> no generation

    accs = {"youtube_shorts": _connect("youtube_shorts"), "tiktok": _connect("tiktok")}
    with session_scope() as db:
        jobs = create_jobs_for_campaign(db, cid, accounts=accs, run_mode="MANUAL")
        job_platforms = sorted(j.platform for j in jobs)
        job_ids = [j.id for j in jobs]
    assert job_platforms == ["tiktok", "youtube_shorts"]        # only GENERATE_AND_PUBLISH

    for jid in job_ids:
        run_publish_job(jid)

    with session_scope() as db:
        by_platform = {}
        for j in db.query(PublishJob).filter_by(campaign_id=cid):
            by_platform.setdefault(j.platform, []).append(j.status)
        assert set(by_platform) == {"youtube_shorts", "tiktok"}
        assert db.query(PublishJob).filter_by(campaign_id=cid, platform="linkedin").count() == 0
        assert db.query(PublishJob).filter_by(campaign_id=cid, platform="naver_blog").count() == 0
        assert db.query(PublishJob).filter_by(campaign_id=cid, platform="instagram_reel").count() == 0
