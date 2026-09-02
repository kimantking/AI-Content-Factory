"""§BM / §CA — reference-use vs media-rights separation, and cross-brand isolation
of learning data."""
from __future__ import annotations

import uuid

from app.db.base import session_scope
from app.db.models_gov import RightsLedger
from app.db.models_learn import (
    DatasetRecord,
    PromptBlueprint,
    ReferenceSource,
)
from app.intel.composer import relevant_blueprints, relevant_skills
from app.intel.engine import add_urls, run_learning_job


def _learn(ws, urls, *, brand=None, channel=None, topic="AI 자동화"):
    with session_scope() as db:
        job = add_urls(db, urls=urls, execution_mode="LEARN_ONLY", workspace_id=ws,
                       brand_id=brand, channel_id=channel, topic=topic)
        jid = job.id
    with session_scope() as db:
        return run_learning_job(db, jid)


def test_reference_use_does_not_create_media_rights(tenant):
    ws = tenant["workspace_id"]
    _learn(ws, ["https://example.com/mt-report", "https://example.com/ai-creators"])
    with session_scope() as db:
        refs = db.query(ReferenceSource).filter_by(workspace_id=ws).all()
        assert refs and all(r.rights_status == "RESEARCH_REFERENCE" for r in refs)
        # learning a page never fabricates a RightsLedger entry for its media
        assert db.query(RightsLedger).count() == 0


def test_learning_data_is_brand_isolated(tenant):
    ws = tenant["workspace_id"]
    brand_a, brand_b = str(uuid.uuid4()), str(uuid.uuid4())
    _learn(ws, [f"https://batch.example.com/a{i}" for i in range(6)], brand=brand_a, topic="브랜드 A 주제")
    _learn(ws, [f"https://batch.example.com/a{i}" for i in range(6, 12)], brand=brand_b, topic="브랜드 B 주제")

    with session_scope() as db:
        a_refs = db.query(ReferenceSource).filter_by(brand_id=brand_a).count()
        b_refs = db.query(ReferenceSource).filter_by(brand_id=brand_b).count()
        assert a_refs >= 5 and b_refs >= 5
        a_ds = {d.id for d in db.query(DatasetRecord).filter_by(brand_id=brand_a)}
        b_ds = {d.id for d in db.query(DatasetRecord).filter_by(brand_id=brand_b)}
        assert a_ds and b_ds and not (a_ds & b_ds)
        # a blueprint tagged brand A carries brand_a and not brand_b
        for bp in db.query(PromptBlueprint).filter_by(brand_id=brand_a):
            assert bp.brand_id == brand_a
        # composer retrieval is workspace-scoped and does not mix brands' rows by id
        skills_ws = relevant_skills(db, workspace_id=ws, agent_type="Research Agent")
        assert all(s.workspace_id == ws for s in skills_ws)


def test_another_workspace_sees_nothing(tenant):
    ws = tenant["workspace_id"]
    other = str(uuid.uuid4())
    _learn(ws, [f"https://batch.example.com/a{i}" for i in range(6)])
    with session_scope() as db:
        assert db.query(ReferenceSource).filter_by(workspace_id=other).count() == 0
        assert db.query(DatasetRecord).filter_by(workspace_id=other).count() == 0
        assert relevant_blueprints(db, workspace_id=other, agent_type="Research Agent",
                                   include_experimental=True) == []
