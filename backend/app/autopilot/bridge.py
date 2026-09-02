from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.autopilot.config import risk_rank
from app.autopilot.context import AutopilotContext
from app.autopilot.recheck import CONTINUE, pre_publish_recheck
from app.config import get_settings
from app.db.base import session_scope
from app.db.models import (
    AutopilotDecision,
    Campaign,
    LearningMemory,
    PublishJob,
    TopicCandidate,
)

_HOUR_BUCKET = {"night": 2, "morning": 8, "afternoon": 14, "evening": 19}


def _recommended_when(session, platform: str, base: datetime, idx: int) -> datetime:
    """Phase 3 TIMING memory if we have enough data, else a staggered default."""
    m = (session.query(LearningMemory)
         .filter(LearningMemory.memory_type == "TIMING",
                 LearningMemory.status.in_(["MODERATE", "STRONG"]))
         .filter(LearningMemory.dimension.like("publish_hour_bucket=%"))
         .first())
    if m:
        bucket = m.dimension.split("=", 1)[1]
        hour = _HOUR_BUCKET.get(bucket, 19)
        when = base.replace(hour=hour, minute=0, second=0, microsecond=0)
        if when <= base:
            when += timedelta(days=1)
        return when + timedelta(minutes=15 * idx)
    return base + timedelta(minutes=30 + 20 * idx)


def produce_from_context(ctx: AutopilotContext, *, run_mode: str) -> dict:
    """Reuse Phase 1-A / 1-B / 2 for one selected candidate. Idempotent by
    candidate_id (crash-safe)."""
    s = get_settings()
    from app.agents.media_runner import run_media_pipeline
    from app.agents.runner import run_pipeline
    from app.publishing.service import create_jobs_for_campaign

    with session_scope() as session:
        cand = session.get(TopicCandidate, ctx.candidate_id)
        if cand is None:
            return {"ok": False, "reason": "candidate missing"}
        if cand.campaign_id:                                   # already produced
            return {"ok": True, "campaign_id": cand.campaign_id, "idempotent": True}
        platforms = [p["platform"] for p in ctx.recommended_platforms] or ["youtube_shorts"]
        cid = str(uuid.uuid4())
        session.add(Campaign(id=cid, topic=ctx.topic, audience_goal=ctx.objective,
                             platforms=platforms, status="WAITING",
                             knowledge_pack=None))
        cand.campaign_id = cid
        cand.status = "PRODUCING"
        session.add(AutopilotDecision(run_id=ctx.run_id, candidate_id=cand.id,
                                      decision_type="produce", selected=True,
                                      reason=f"campaign {cid} for {platforms}",
                                      config_version=s.autopilot_config_version))

    # Phase 1-A + 1-B (own sessions inside)
    st1 = run_pipeline(cid, ctx.topic, ctx.objective, platforms)
    if st1.get("status") != "SUCCESS":
        with session_scope() as session:
            session.get(TopicCandidate, ctx.candidate_id).status = "CANCELLED"
        return {"ok": False, "campaign_id": cid, "reason": f"phase1a {st1.get('status')}"}
    run_media_pipeline(cid, platforms)

    # pre-publish recheck (sunk cost is not a reason to publish a dead trend)
    with session_scope() as session:
        rc = pre_publish_recheck(session, ctx.candidate_id)
    if rc["verdict"] != CONTINUE:
        return {"ok": True, "campaign_id": cid, "published": False,
                "recheck": rc, "reason": f"recheck {rc['verdict']}"}

    # Phase 7 governance gate (§148): FULL_AUTO cannot bypass. A BLOCK / HUMAN_REVIEW
    # holds the candidate here rather than creating a doomed publish job.
    if getattr(s, "governance_enforce", True):
        with session_scope() as session:
            try:
                from app.governance.engine import govern_campaign

                gov = govern_campaign(session, campaign_id=cid, run_mode=run_mode, stage="post_render")
            except Exception as _ge:  # noqa: BLE001 — fail safe
                gov = {"decision": "HUMAN_REVIEW", "publishable": False,
                       "reason_codes": [f"GOVERNANCE.ERROR:{_ge}"]}
            if not gov.get("publishable"):
                cand = session.get(TopicCandidate, ctx.candidate_id)
                if cand:
                    cand.status = "GOVERNANCE_HOLD"
                session.add(AutopilotDecision(
                    run_id=ctx.run_id, candidate_id=ctx.candidate_id,
                    decision_type="governance_hold", selected=False,
                    reason=f"governance {gov.get('decision')}: {', '.join(gov.get('reason_codes', []))}"[:400],
                    config_version=s.autopilot_config_version))
        if not gov.get("publishable"):
            return {"ok": True, "campaign_id": cid, "published": False,
                    "governance": gov, "reason": f"governance {gov.get('decision')}"}

    # Phase 2: create jobs. Risk matrix overrides the run mode.
    auto = run_mode == "FULL_AUTO"
    if risk_rank(ctx.risk_level) >= risk_rank("CRITICAL"):
        job_mode = "MANUAL"                       # CRITICAL never auto-publishes
    elif risk_rank(ctx.risk_level) >= risk_rank("HIGH"):
        job_mode = "SEMI_AUTO"                    # HIGH always needs human approval
    else:
        job_mode = "FULL_AUTO" if auto else "SEMI_AUTO"

    base = datetime.now(timezone.utc)
    with session_scope() as session:
        schedule = {}
        for i, p in enumerate(platforms):
            schedule[p] = _recommended_when(session, p, base, i)
        jobs = create_jobs_for_campaign(session, cid, accounts={}, schedule=schedule,
                                        run_mode=job_mode, dry_run=s.dry_run)
        session.get(TopicCandidate, ctx.candidate_id).status = "SCHEDULED"
        session.add(AutopilotDecision(run_id=ctx.run_id, candidate_id=ctx.candidate_id,
                                      decision_type="publish_plan", selected=True,
                                      reason=f"{len(jobs)} jobs, mode={job_mode}, risk={ctx.risk_level}",
                                      config_version=s.autopilot_config_version))
        job_ids = [j.id for j in jobs]

    return {"ok": True, "campaign_id": cid, "published": False, "scheduled_jobs": job_ids,
            "job_mode": job_mode, "recheck": rc}
