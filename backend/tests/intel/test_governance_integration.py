"""§BM / §BN / §BW — reference-use vs media rights, and generated-vs-reference
similarity routed through Phase 7 governance."""
from __future__ import annotations

import uuid

import pytest

from app.db.base import session_scope
from app.db.models import PlatformContent, Script
from app.intel.engine import add_urls, run_learning_job
from app.intel.reference_guard import check_against_references


@pytest.fixture
def learned_campaign(tenant):
    """A tenant campaign with 2 learned references attached."""
    from app.db.models import Campaign
    cid = str(uuid.uuid4())
    ws = tenant["workspace_id"]
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="AI 번역", audience_goal="VIEWS",
                        platforms=["youtube_shorts"], status="SUCCESS",
                        workspace_id=ws, brand_id=tenant["brand_id"], channel_id=tenant["channel_id"],
                        execution_mode="CREATE_AND_LEARN"))
        job = add_urls(db, urls=["https://example.com/mt-report", "https://example.com/ai-creators"],
                       execution_mode="CREATE_AND_LEARN", workspace_id=ws,
                       brand_id=tenant["brand_id"], channel_id=tenant["channel_id"],
                       campaign_id=cid, topic="AI 번역")
        jid = job.id
    with session_scope() as db:
        run_learning_job(db, jid)
    return cid, ws


def test_reference_guard_flags_near_copy(learned_campaign):
    cid, ws = learned_campaign
    with session_scope() as db:
        # pull one reference's own chunk text and pretend the script "wrote" it
        from app.db.models_learn import ReferenceChunk, ReferenceSource
        r = db.query(ReferenceSource).filter_by(campaign_id=cid).first()
        chunks = db.query(ReferenceChunk).filter_by(reference_id=r.id).all()
        near_copy = "\n".join(c.text for c in chunks)
        res = check_against_references(db, campaign_id=cid, workspace_id=ws,
                                      items={"SCRIPT": near_copy})
    assert res["n_references"] == 2
    assert res["decision"] == "FIX_REQUIRED"
    assert res["matches"] and res["matches"][0]["kind"] == "SCRIPT"


def test_reference_guard_allows_original_text(learned_campaign):
    cid, ws = learned_campaign
    with session_scope() as db:
        res = check_against_references(db, campaign_id=cid, workspace_id=ws, items={
            "SCRIPT": "완전히 다른 주제입니다. 반려동물 사료 시장의 계절성과 재고 관리에 대해 다룹니다. "
                      "여름철 습식 사료 수요가 늘어난다는 자체 판매 데이터를 예시로 듭니다."})
    assert res["decision"] == "ALLOW" and not res["matches"]


def test_governance_routes_reference_similarity_to_fix(learned_campaign):
    """A campaign whose script is a near-copy of a learned reference -> governance
    FIX_REQUIRED (not publishable) via the wired sub-check."""
    from app.db.base import session_scope as ss
    from app.governance.engine import govern_campaign

    cid, ws = learned_campaign
    with ss() as db:
        from app.db.models_learn import ReferenceChunk, ReferenceSource
        r = db.query(ReferenceSource).filter_by(campaign_id=cid).first()
        near = "\n".join(c.text for c in db.query(ReferenceChunk).filter_by(reference_id=r.id).all())
        db.add(Script(campaign_id=cid, platform="MASTER", body=near, word_count=50,
                      qa_passed=True, qa_report={}, ai_slop_score=10.0, naturalness={}))
        db.add(PlatformContent(campaign_id=cid, platform="youtube_shorts", content_type="SHORT_VIDEO",
                               hook="AI 번역", title="AI가 바꾸는 번역", caption="", script="본문",
                               status="PLANNED", payload={}))
    with ss() as db:
        res = govern_campaign(db, campaign_id=cid, platform="youtube_shorts",
                              stage="pre_publish", run_mode="FULL_AUTO")
    assert "ORIGINALITY.REFERENCE_TOO_SIMILAR" in res["reason_codes"]
    assert res["decision"] in ("FIX_REQUIRED", "HUMAN_REVIEW", "BLOCK")
    assert res["publishable"] is False
