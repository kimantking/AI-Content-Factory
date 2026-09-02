from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.autopilot.controller import run_autopilot
from app.autopilot.emergency import emergency_stop
from app.autopilot.recheck import pre_publish_recheck
from app.db.base import session_scope
from app.db.models import (
    AutopilotDecision,
    AutopilotRun,
    Campaign,
    Publication,
    PublishJob,
    TopicCandidate,
)
from app.trends.faults import trend_faults

pytestmark = pytest.mark.integration


def _real_campaign() -> str:
    cid = str(uuid.uuid4())
    with session_scope() as s:
        s.add(Campaign(id=cid, topic="t", platforms=["youtube_shorts"], status="SUCCESS"))
    return cid


def test_shadow_produces_zero_content(_autopilot_defaults):
    r = run_autopilot("SHADOW")
    assert r["status"] == "SUCCESS"
    assert r["produced"] == 0 and r["published"] == 0
    assert r["selected"]                                  # it DID compute candidates
    with session_scope() as s:
        assert s.query(Campaign).count() == 0            # nothing created
        assert s.query(PublishJob).count() == 0          # nothing scheduled
        assert s.query(TopicCandidate).count() > 0
        assert s.query(AutopilotDecision).count() > 0    # decisions logged


def test_full_autopilot_mock_e2e(_autopilot_defaults):
    s = _autopilot_defaults
    s.autopilot_daily_content_min = 1
    s.autopilot_daily_content_max = 1
    s.autopilot_stage1_keep = 8
    s.autopilot_stage2_keep = 3
    s.autopilot_min_opportunity_score = 40

    r = run_autopilot("FULL_AUTO")
    assert r["status"] in ("SUCCESS", "PAUSED")
    assert r["produced"] >= 1

    with session_scope() as sess:
        camps = sess.query(Campaign).all()
        assert camps and all(c.status == "SUCCESS" for c in camps)
        assert sess.query(PublishJob).count() >= 1
        sched = sess.query(TopicCandidate).filter_by(status="SCHEDULED").count()
        prod = sess.query(TopicCandidate).filter(TopicCandidate.campaign_id.isnot(None)).count()
        assert prod >= 1 and sched >= 1
        # decision log has selection + produce + publish_plan
        types = {d.decision_type for d in sess.query(AutopilotDecision)}
        assert {"selection", "produce"} <= types


def test_crash_recovery_no_duplicate_campaign(_autopilot_defaults):
    s = _autopilot_defaults
    s.autopilot_daily_content_max = 1
    s.autopilot_stage1_keep = 6
    s.autopilot_stage2_keep = 2
    s.autopilot_min_opportunity_score = 40

    r1 = run_autopilot("FULL_AUTO")
    run_id = r1["run_id"]
    with session_scope() as sess:
        n_camp = sess.query(Campaign).count()
        cand_to_camp = {c.id: c.campaign_id for c in
                        sess.query(TopicCandidate).filter(TopicCandidate.campaign_id.isnot(None))}

    # "worker died" -> resume the same run
    r2 = run_autopilot("FULL_AUTO", resume_run_id=run_id)
    assert r2["status"] in ("SUCCESS", "PAUSED")
    with session_scope() as sess:
        assert sess.query(Campaign).count() == n_camp           # no duplicate campaigns
        for cid, camp in cand_to_camp.items():
            assert sess.get(TopicCandidate, cid).campaign_id == camp


def test_dead_trend_pre_publish_recheck_cancels(_autopilot_defaults):
    cand_id = str(uuid.uuid4())
    with session_scope() as s:
        s.add(TopicCandidate(
            id=cand_id, run_id=str(uuid.uuid4()), topic="속보성 이슈", angle="a",
            topic_cluster_id="news", trend_type="BREAKING", status="PRODUCING",
            opportunity_score=90.0,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=2),   # already expired
            explanation={"score": {"opportunity_score": 90.0}},
        ))
    with session_scope() as s:
        rc = pre_publish_recheck(s, cand_id)
    assert rc["verdict"] in ("CANCEL", "HOLD")
    with session_scope() as s:
        assert s.get(TopicCandidate, cand_id).status == "CANCELLED" or rc["verdict"] == "HOLD"


def test_high_risk_forces_manual_job_mode(_autopilot_defaults):
    from app.autopilot.context import AutopilotContext
    from app.autopilot.bridge import produce_from_context

    _autopilot_defaults.autopilot_daily_content_max = 1
    ctx = AutopilotContext(
        candidate_id="", run_id=str(uuid.uuid4()), topic="선거 여론조사 해석",
        angle="데이터로 착시 짚기", objective="BALANCED", opportunity_score=80.0,
        platform_scores={"youtube_shorts": 80}, trend_evidence={}, audience="일반",
        recommended_platforms=[{"platform": "youtube_shorts", "content_type": "SHORT_VIDEO",
                                "platform_score": 80, "account_connected": False, "capability_note": None}],
        recommended_content_types=["SHORT_VIDEO"], production_profile="STANDARD",
        recommended_hook_direction="", estimated_cost=0.3, risk_level="CRITICAL",
        risk_categories=["ELECTION"], deadline=None, source_ids=["own_analytics"],
    )
    cand_id = str(uuid.uuid4())
    with session_scope() as s:
        s.add(TopicCandidate(id=cand_id, run_id=ctx.run_id, topic=ctx.topic, angle=ctx.angle,
                             status="SELECTED", risk_level="CRITICAL", opportunity_score=80.0,
                             explanation={"score": {"opportunity_score": 80.0}}))
    ctx.candidate_id = cand_id
    res = produce_from_context(ctx, run_mode="FULL_AUTO")
    assert res["ok"]
    # CRITICAL risk -> jobs created MANUAL (never auto-published) OR held by recheck
    assert res.get("job_mode") in ("MANUAL", None)
    if res.get("scheduled_jobs"):
        with session_scope() as s:
            for jid in res["scheduled_jobs"]:
                assert s.get(PublishJob, jid).run_mode == "MANUAL"


def test_all_trend_sources_down_yields_no_candidates(_autopilot_defaults):
    trend_faults.arm("*", "PROVIDER_ERROR", times=999)
    r = run_autopilot("SHADOW")
    assert r["status"] == "SUCCESS"          # graceful, not a crash
    assert r["produced"] == 0
    with session_scope() as s:
        assert s.query(Campaign).count() == 0


def test_watchdog_pauses_on_post_limit(_autopilot_defaults):
    s = _autopilot_defaults
    s.autopilot_daily_post_limit = 0
    s.autopilot_daily_content_max = 1
    s.autopilot_stage1_keep = 6
    s.autopilot_stage2_keep = 2
    s.autopilot_min_opportunity_score = 40
    cid = _real_campaign()
    with session_scope() as sess:
        for _ in range(3):
            job = PublishJob(campaign_id=cid, platform="youtube_shorts", status="PUBLISHED",
                             idempotency_key=str(uuid.uuid4()))
            sess.add(job)
            sess.flush()
            sess.add(Publication(publish_job_id=job.id, campaign_id=cid,
                                 platform="youtube_shorts", status="PUBLISHED",
                                 published_at=datetime.now(timezone.utc)))
    r = run_autopilot("FULL_AUTO")
    assert r["status"] == "PAUSED"
    with session_scope() as sess:
        run = sess.get(AutopilotRun, r["run_id"])
        assert "TOO_MANY_POSTS" in (run.pause_reason or "")


def test_emergency_stop_halts_everything(_autopilot_defaults):
    cid = _real_campaign()
    with session_scope() as s:
        run = AutopilotRun(mode="FULL_AUTO", objective="BALANCED", status="RUNNING")
        s.add(run)
        s.flush()
        s.add(TopicCandidate(run_id=run.id, topic="t", angle="a", status="SELECTED",
                             opportunity_score=80.0))
        s.add(PublishJob(campaign_id=cid, platform="youtube_shorts",
                         status="READY", idempotency_key=str(uuid.uuid4())))
    with session_scope() as s:
        res = emergency_stop(s, actor="user")
    assert res["held_runs"] >= 1 and res["held_candidates"] >= 1 and res["held_jobs"] >= 1
    with session_scope() as s:
        assert all(r.status == "STOPPED" for r in s.query(AutopilotRun))
        assert all(c.status == "CANCELLED" for c in s.query(TopicCandidate).filter_by(status="CANCELLED"))
    # a new run is refused while the stop flag is set
    r = run_autopilot("FULL_AUTO")
    assert r["status"] == "STOPPED"
