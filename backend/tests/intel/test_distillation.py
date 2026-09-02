"""§S-§X / §BP-§BY — Prompt Distillation: video blueprint generation from many
profiles, single-source guard, multi-reference confidence, promotion state machine,
copyright non-duplication."""
from __future__ import annotations

import uuid

import pytest

from app.db.base import session_scope
from app.db.models_learn import (
    PromptBlueprint,
    PromptBlueprintEvidence,
    ReferenceSource,
)
from app.intel import distillation
from app.intel.engine import add_urls, run_learning_job
from tests.intel.conftest import video_profile


def _video_learn_job(ws, n, *, common=True, topic="좋은 AI 쇼츠 편집"):
    urls = [f"https://batch.example.com/a{i}" for i in range(n)]
    vps = {u: video_profile(i, common=common) for i, u in enumerate(urls)}
    with session_scope() as db:
        # force these to be treated as video references
        job = add_urls(db, urls=urls, execution_mode="LEARN_ONLY", workspace_id=ws,
                       topic=topic, purpose="VIDEO_REFERENCE", video_profiles=vps)
        jid = job.id
    with session_scope() as db:
        res = run_learning_job(db, jid)
    return jid, res


def test_video_distillation_from_many_profiles(tenant):
    ws = tenant["workspace_id"]
    jid, res = _video_learn_job(ws, 30, common=True)
    assert res["ok"] and res["counters"]["ready"] >= 10

    with session_scope() as db:
        bps = db.query(PromptBlueprint).filter_by(workspace_id=ws).all()
        agents = {b.agent_type for b in bps}
        # video sub-engine blueprints exist
        assert {"Video Editor", "B-roll Director", "Subtitle Director", "Audio Director"} & agents
        for b in bps:
            # multi-reference -> sample_size reflects the references, not 1
            assert b.sample_size >= 3
            # evidence is traceable
            ev = db.query(PromptBlueprintEvidence).filter_by(blueprint_id=b.id).count()
            assert ev == b.sample_size
            assert b.status in ("EXPERIMENTAL", "CANDIDATE")   # never auto-PROMOTED
        # an editing blueprint carries the "short scene rhythm" guidance
        editor = next((b for b in bps if b.agent_type == "Video Editor"), None)
        assert editor and any("리듬" in i or "짧" in i for i in editor.instructions)


def test_single_reference_cannot_pass_experimental(tenant):
    ws = tenant["workspace_id"]
    jid, res = _video_learn_job(ws, 1, common=True)
    with session_scope() as db:
        bps = db.query(PromptBlueprint).filter_by(workspace_id=ws).all()
        assert bps, "expected at least one OBSERVED/EXPERIMENTAL blueprint"
        for b in bps:
            assert b.sample_size == 1
            assert b.status in ("OBSERVED", "EXPERIMENTAL")
            bid = b.id
        # cannot advance a single-source blueprint past EXPERIMENTAL
        r = distillation.advance_status(db, bid, "CANDIDATE", actor="user")
        assert r["ok"] is False and "single-reference" in r["error"]


def test_promotion_state_machine_and_rollback(tenant):
    ws = tenant["workspace_id"]
    jid, res = _video_learn_job(ws, 8, common=True)
    with session_scope() as db:
        bp = db.query(PromptBlueprint).filter_by(workspace_id=ws).first()
        bid = bp.id
        start = bp.status

        # invalid jump is rejected (nothing reaches PROMOTED without VALIDATED)
        assert distillation.advance_status(db, bid, "PROMOTED", actor="user")["ok"] is False
        # walk the ladder from wherever distillation placed it
        ladder = ["OBSERVED", "EXPERIMENTAL", "CANDIDATE", "VALIDATED"]
        for nxt in ladder[ladder.index(start) + 1:]:
            assert distillation.advance_status(db, bid, nxt, actor="user")["ok"], nxt
        assert db.get(PromptBlueprint, bid).status == "VALIDATED"
        # system cannot auto-promote (AUTO_PROMOTE_LEARNED_PROMPTS is false)
        assert distillation.advance_status(db, bid, "PROMOTED", actor="system")["ok"] is False
        # a human (or a validated experiment) can
        assert distillation.advance_status(db, bid, "PROMOTED", actor="user")["ok"]
        assert db.get(PromptBlueprint, bid).status == "PROMOTED"
        # rollback
        assert distillation.rollback(db, bid, actor="user")["ok"]
        assert db.get(PromptBlueprint, bid).status == "VALIDATED"


def test_internal_evidence_outranks_and_bumps_confidence(tenant):
    ws = tenant["workspace_id"]
    jid, res = _video_learn_job(ws, 5, common=True)
    with session_scope() as db:
        bp = db.query(PromptBlueprint).filter_by(workspace_id=ws).first()
        bid, before_conf, before_n = bp.id, bp.confidence, bp.sample_size
        distillation.add_internal_evidence(db, bid, campaign_id=str(uuid.uuid4()),
                                           metric_delta={"retention": +0.08},
                                           observation="our A/B: short-scene cut lifted retention")
    with session_scope() as db:
        bp = db.get(PromptBlueprint, bid)
        assert bp.sample_size == before_n + 1 and bp.confidence > before_conf
        ev = db.query(PromptBlueprintEvidence).filter_by(
            blueprint_id=bid, evidence_type="INTERNAL_CONTENT").count()
        assert ev == 1


def test_copyright_source_text_not_copied_into_blueprint(tenant):
    """§BX — a long verbatim passage from a reference must not appear in a blueprint
    or a skill note."""
    ws = tenant["workspace_id"]
    marker = "이문장은저작권이있는고유한원문표현이며그대로복제되면안된다" * 2
    c = pytest.importorskip("app.intel.fetch").MockReferenceClient()
    import app.intel.fetch as F
    from tests.intel.conftest import _article

    body = _article("저작권 기사", [marker, "일반적인 배경 설명 문장.", "또 다른 일반 문장이다.",
                                 "예시를 들어 설명한다.", "결론적으로 정리한다."])
    for i in range(4):
        c.register(f"https://copyright.example.com/{i}", body=body)
    F.set_client(c)
    urls = [f"https://copyright.example.com/{i}" for i in range(4)]
    with session_scope() as db:
        job = add_urls(db, urls=urls, execution_mode="LEARN_ONLY", workspace_id=ws,
                       topic="저작권", purpose="STYLE_REFERENCE")
        jid = job.id
    with session_scope() as db:
        run_learning_job(db, jid)
    with session_scope() as db:
        for b in db.query(PromptBlueprint).filter_by(workspace_id=ws).all():
            blob = " ".join(b.instructions + b.constraints + b.positive_patterns + b.negative_patterns)
            assert marker not in blob
        from app.db.models_learn import LearnedSkillNote
        for n in db.query(LearnedSkillNote).filter_by(workspace_id=ws).all():
            assert marker not in (n.rule + n.rationale)
