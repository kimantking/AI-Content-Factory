"""Phase 9 §111 — the 12 Phase 1-8 safety invariants, re-verified as a block.
Any failure here is a Phase 9 completion-gate blocker."""
from __future__ import annotations

import uuid

import pytest

from app.db.base import session_scope
from app.db.models import Campaign
from tests.phase9.conftest import ollama_reachable

pytestmark = [pytest.mark.phase9, pytest.mark.smoke]


# 1 — LEARN_ONLY -> 0 production
def test_inv_learn_only_zero_production():
    from app.db.models import Asset, MediaTask, PublishJob
    from app.intel import fetch as F
    from app.intel.engine import add_urls, run_learning_job

    c = F.MockReferenceClient()
    for i in range(6):
        c.register(f"https://inv.example.com/a{i}",
                   body=f"<html><head><title>t{i}</title></head><body><main><h1>t{i}</h1>"
                        f"<p>연구에 따르면 자동화가 {40 + i}% 라고 한다. 전문가는 검수가 중요하다 말했다. "
                        f"예시 {i}에서 사람이 확인한다. 저작권은 사람 몫이다.</p></main></body></html>")
    F.set_client(c)
    ws = str(uuid.uuid4())
    try:
        with session_scope() as db:
            j = add_urls(db, urls=[f"https://inv.example.com/a{i}" for i in range(6)],
                         execution_mode="LEARN_ONLY", workspace_id=ws, topic="t")
            jid = j.id
        with session_scope() as db:
            run_learning_job(db, jid)
        with session_scope() as db:
            assert db.query(Campaign).filter_by(workspace_id=ws).count() == 0
            assert db.query(Asset).count() == 0
            assert db.query(MediaTask).count() == 0
            assert db.query(PublishJob).count() == 0
    finally:
        F.set_client(F.MockReferenceClient())


# 2 & 3 — SNS OFF -> generation 0, publish 0
def test_inv_sns_off_zero_generation_and_publish():
    from app.db.models import PlatformContent, PublishJob
    from app.db.models_learn import CampaignPlatformSelection
    from app.agents.runner import run_pipeline

    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="off-invariant", audience_goal="BALANCED",
                        platforms=["youtube_shorts"], status="WAITING"))
        db.flush()
        db.add(CampaignPlatformSelection(campaign_id=cid, platform="tiktok", content_type="short",
                                         mode="DISABLED", user_explicit=True))
    run_pipeline(cid, "off-invariant", "BALANCED", ["youtube_shorts"])
    with session_scope() as db:
        assert db.query(PlatformContent).filter_by(campaign_id=cid, platform="tiktok").count() == 0
        assert db.query(PublishJob).filter_by(campaign_id=cid, platform="tiktok").count() == 0


# 4 — LOCAL_ONLY -> 0 cloud calls
def test_inv_local_only_zero_cloud(_base_settings, monkeypatch):
    _base_settings.allow_cloud_fallback = False
    _base_settings.ollama_enabled = True
    from app.ai_router import execute as ex
    from app.agents import model_gateway as gw
    from app.providers.errors import ProviderError
    from tests.ai_router.conftest import RecordingProvider

    dead_local = RecordingProvider("ollama", "gemma3:4b", raise_error=ProviderError("refused"))
    cloud = RecordingProvider("anthropic", "claude-sonnet-5", payload={"x": 1})
    monkeypatch.setattr(ex, "_provider_for",
                        lambda mid, prov: dead_local if prov == "ollama" else cloud)
    with session_scope() as db:
        r = gw.routed_complete(agent_name="Hook Agent", task="hook", system="s", user="u",
                               context={}, session=db, campaign_id=None)
    assert not cloud.calls
    assert r.routed is False and r.provider in ("mock", "")


# 5 — Governance gate: a job with no governance clearance never reaches PUBLISHED
def test_inv_governance_block_zero_publish(_base_settings):
    _base_settings.governance_enforce = True
    from app.publishing.engine import run_publish_job
    from app.db.models import PublishJob, Script
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="gov-block", audience_goal="BALANCED",
                        platforms=["youtube_shorts"], status="SUCCESS"))
        db.flush()
        # a script that leans on an UNVERIFIED claim -> governance must not clear it
        db.add(Script(campaign_id=cid, platform="MASTER",
                      body="확인되지 않은 주장: 이 제품은 100% 효과가 있다고 한다.", word_count=8,
                      qa_passed=True))
        job = PublishJob(campaign_id=cid, platform="youtube_shorts", content_type="short",
                         status="READY", run_mode="MANUAL", approval_status="APPROVED",
                         idempotency_key=str(uuid.uuid4()))
        db.add(job)
        db.flush()
        jid = job.id
    res = run_publish_job(jid)
    assert res["status"] != "PUBLISHED", res
    with session_scope() as db:
        j = db.get(PublishJob, jid)
        assert j.remote_post_id is None
        assert j.status in ("BLOCKED", "HUMAN_REVIEW", "WAITING_APPROVAL", "FIX_REQUIRED",
                            "FAILED", "DRAFT", "READY")


# 6 — Viewer cannot do a protected write
def test_inv_viewer_write_forbidden():
    from app.auth.context import AuthContext
    ctx = AuthContext(user_id="u", role="VIEWER", memberships={"w": "VIEWER"}, workspace_id="w")
    with pytest.raises(Exception):
        ctx.require("brand.write")


# 7 — tenant isolation: no cross-workspace leak in library
def test_inv_tenant_isolation_library():
    from app.library.service import list_content
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    with session_scope() as db:
        db.add_all([
            Campaign(id=str(uuid.uuid4()), topic="A camp", audience_goal="BALANCED",
                     platforms=["youtube_shorts"], status="SUCCESS", workspace_id=a),
            Campaign(id=str(uuid.uuid4()), topic="B camp", audience_goal="BALANCED",
                     platforms=["youtube_shorts"], status="SUCCESS", workspace_id=b),
        ])
    with session_scope() as db:
        out = list_content(db, workspace_id=a)
    topics = {c["topic"] for c in out["items"]}
    assert topics == {"A camp"}


# 8 — queue OFF race: platform turned off AFTER queue -> 0 remote
def test_inv_queue_off_race_zero_remote():
    from app.publishing.engine import run_publish_job
    from app.db.models import PublishJob
    from app.db.models_learn import CampaignPlatformSelection
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="queue-off", audience_goal="BALANCED",
                        platforms=["tiktok"], status="SUCCESS"))
        db.flush()
        db.add(CampaignPlatformSelection(campaign_id=cid, platform="tiktok", content_type="short",
                                         mode="GENERATE_AND_PUBLISH", user_explicit=True))
        job = PublishJob(campaign_id=cid, platform="tiktok", content_type="short",
                         status="READY", run_mode="MANUAL", approval_status="APPROVED",
                         idempotency_key=str(uuid.uuid4()))
        db.add(job)
        db.flush()
        jid = job.id
    # user flips it OFF after the job is queued
    with session_scope() as db:
        sel = db.query(CampaignPlatformSelection).filter_by(campaign_id=cid, platform="tiktok").one()
        sel.mode = "DISABLED"
    res = run_publish_job(jid)
    assert res["status"] == "BLOCKED"
    with session_scope() as db:
        assert db.get(PublishJob, jid).remote_post_id is None


# 9 — single-scene repair does not regenerate unrelated scenes
def test_inv_single_scene_repair_scoped():
    from app.edit.nl_to_request import apply_edit, impact_of, parse_instruction
    scenes = [{"scene_order": i, "still_asset_id": f"a{i}", "voice_asset_id": f"v{i}",
               "camera_motion": "SLOW_ZOOM_IN", "cinematic_motion": "", "estimated_duration": 4.0,
               "narration": f"n{i}"} for i in range(1, 6)]
    req = parse_instruction("3번 장면 b-roll을 교체해줘")
    new, meta = apply_edit(scenes, {}, req)
    imp = impact_of(scenes, new, old_meta={}, new_meta=meta)
    assert imp["rebuild_scene_clips"] == [3]


# 10 — budget hard limit -> no over-budget paid execution
def test_inv_budget_hard_limit(_base_settings):
    from app.services.budget import check_budget
    from app.providers.errors import ProviderError
    _base_settings.campaign_budget_usd = 0.01
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="budget-inv", audience_goal="BALANCED",
                        platforms=["youtube_shorts"], status="RUNNING"))
        db.flush()
        from app.db.models import CostLog
        db.add(CostLog(campaign_id=cid, agent_name="x", kind="LLM", amount_usd=0.05))
    with session_scope() as db:
        with pytest.raises((ProviderError, Exception)):
            check_budget(db, cid)


# 11 — direct provider bypass still 0
def test_inv_direct_provider_bypass_zero():
    import re
    from pathlib import Path
    app = Path(__file__).resolve().parents[2] / "app"
    for rel in ("agents/nodes.py", "agents/media_nodes.py", "autopilot/pipeline.py"):
        src = (app / rel).read_text(encoding="utf-8")
        assert not re.search(r"^[^#\n]*\bget_llm_provider\s*\(", src, re.M), rel


# 12 — PromptComposer stays on the production agent flow
def test_inv_prompt_composer_on_agent_flow(_base_settings):
    from app.agents import model_gateway as gw
    from app.db.models_learn import LearnedSkillNote
    ws = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="composer-inv", audience_goal="BALANCED",
                        platforms=["youtube_shorts"], status="RUNNING", workspace_id=ws))
        db.add(LearnedSkillNote(workspace_id=ws, agent_type="Hook Agent", skill_category="c",
                                rule="불변식 확인용 훅 규칙", confidence=0.8, sample_size=6,
                                status="CANDIDATE"))
        db.flush()
        r = gw.routed_complete(agent_name="Hook Agent", task="hook", system="BASE", user="{}",
                               context={}, session=db, campaign_id=cid, workspace_id=ws)
    assert r.prompt_lineage.get("prompt_composer_used") is True
    assert r.prompt_lineage.get("skill_ids")


def test_ollama_still_local_verified():
    if not ollama_reachable():
        pytest.skip("Ollama not reachable in this environment")
    from app.providers.ollama_llm import OllamaLLMProvider
    p = OllamaLLMProvider(base_url="http://localhost:11434", model="gemma3:4b", timeout_seconds=60)
    resp = p.complete(system='Return {"ok":true} as JSON.', user="ping", task="classification",
                      context={})
    import json
    assert isinstance(json.loads(resp.text), dict)
