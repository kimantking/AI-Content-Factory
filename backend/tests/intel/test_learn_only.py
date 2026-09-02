"""§BO / §BD / §CJ — LEARN_ONLY and REFERENCE_ONLY must never do production work."""
from __future__ import annotations

import uuid

import pytest

from app.db.base import session_scope
from app.db.models import Asset, Campaign, MediaTask, PlatformContent, PublishJob
from app.intel.engine import add_urls, run_learning_job
from app.db.models_learn import (
    DatasetRecord,
    LearningJob,
    PromptBlueprint,
    ReferenceSource,
    LearnedSkillNote,
)


def _run(urls, mode, ws, topic="AI 자동화", **kw):
    with session_scope() as db:
        job = add_urls(db, urls=urls, execution_mode=mode, workspace_id=ws, topic=topic, **kw)
        jid = job.id
    with session_scope() as db:
        res = run_learning_job(db, jid)
    return jid, res


def test_learn_only_learns_but_creates_no_production_rows(tenant):
    ws = tenant["workspace_id"]
    urls = [f"https://batch.example.com/a{i}" for i in range(12)]
    jid, res = _run(urls, "LEARN_ONLY", ws)

    assert res["ok"]
    with session_scope() as db:
        assert db.query(ReferenceSource).filter_by(workspace_id=ws).count() >= 10
        assert db.query(DatasetRecord).filter_by(workspace_id=ws).count() > 0
        assert db.query(PromptBlueprint).filter_by(workspace_id=ws).count() > 0
        assert db.query(LearnedSkillNote).filter_by(workspace_id=ws).count() > 0
        # NOTHING produced
        assert db.query(Campaign).count() == 0
        assert db.query(PlatformContent).count() == 0
        assert db.query(Asset).count() == 0
        assert db.query(MediaTask).count() == 0
        assert db.query(PublishJob).count() == 0


def test_learn_only_without_topic_is_allowed(tenant):
    jid, res = _run([f"https://batch.example.com/a{i}" for i in range(6)], "LEARN_ONLY",
                    tenant["workspace_id"], topic="")
    assert res["ok"] and res["counters"]["ready"] >= 1


def test_reference_only_stores_but_writes_no_dataset_or_prompt(tenant):
    ws = tenant["workspace_id"]
    jid, res = _run(["https://example.com/mt-report", "https://example.com/ai-creators"],
                    "REFERENCE_ONLY", ws)
    assert res["reference_only"] is True
    with session_scope() as db:
        assert db.query(ReferenceSource).filter_by(workspace_id=ws).count() == 2
        assert db.query(DatasetRecord).filter_by(workspace_id=ws).count() == 0
        assert db.query(PromptBlueprint).filter_by(workspace_id=ws).count() == 0
        assert db.query(LearnedSkillNote).filter_by(workspace_id=ws).count() == 0


def test_learn_only_campaign_creates_no_publish_jobs(make_learn_campaign):
    """A campaign flagged LEARN_ONLY: create_jobs_for_campaign is a no-op."""
    from app.publishing.service import create_jobs_for_campaign

    cid = make_learn_campaign(execution_mode="LEARN_ONLY", platforms=["youtube_shorts"])
    with session_scope() as db:
        db.add(PlatformContent(campaign_id=cid, platform="youtube_shorts",
                               content_type="SHORT_VIDEO", title="t", script="s", status="PLANNED",
                               payload={}))
    with session_scope() as db:
        jobs = create_jobs_for_campaign(db, cid, run_mode="MANUAL")
    assert jobs == []
    with session_scope() as db:
        assert db.query(PublishJob).filter_by(campaign_id=cid).count() == 0


def test_production_guard_raises_for_learn_only_entrypoints():
    from app.intel.modes import ProductionSideEffectBlocked, assert_no_production_side_effects

    for op in ("campaign_production", "ai_image_generation", "ai_video_generation",
               "tts_production", "final_render", "publish_job", "sns_api_call"):
        with pytest.raises(ProductionSideEffectBlocked):
            assert_no_production_side_effects("LEARN_ONLY", op)
