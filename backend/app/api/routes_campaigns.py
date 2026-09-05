from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import Base, get_db
from app.db.models import (
    AgentRun,
    Campaign,
    CostLog,
    Hook,
    ResearchSource,
    Script,
    Strategy,
    VerifiedFact,
)
from app.schemas.api import CampaignDetail, CampaignSummary, CreateCampaignRequest

router = APIRouter(prefix="/api", tags=["campaigns"])

PIPELINE_STEPS = [
    "create_campaign", "research", "fact_check", "research_fix",
    "strategize", "hook", "write_script", "qa_script", "persist",
]
_STEP_ORDER = {s: i for i, s in enumerate(PIPELINE_STEPS)}


def _enqueue(campaign: Campaign) -> None:
    s = get_settings()
    from app.celery_app import celery_app  # noqa: F401  (ensure configured broker)
    from app.tasks import run_campaign_task

    args = [campaign.id, campaign.topic, campaign.audience_goal, campaign.platforms]
    if s.run_inline:
        run_campaign_task.apply(args=args)
    else:
        try:
            run_campaign_task.delay(*args)
        except Exception as e:  # broker unreachable -> run in-process as fallback
            campaign_id = campaign.id
            import logging

            logging.getLogger("acf").warning("broker unavailable (%s); running inline", e)
            run_campaign_task.apply(args=args)


@router.post("/campaigns", response_model=CampaignSummary, status_code=201)
def create_campaign(payload: CreateCampaignRequest, db: Session = Depends(get_db)) -> CampaignSummary:
    camp = Campaign(
        topic=payload.topic.strip(),
        audience_goal=payload.normalized_goal(),
        platforms=payload.platforms,
        status="WAITING",
        current_step=None,
    )
    db.add(camp)
    db.commit()
    db.refresh(camp)
    _enqueue(camp)
    db.refresh(camp)
    return _summary(camp)


@router.get("/campaigns", response_model=list[CampaignSummary])
def list_campaigns(db: Session = Depends(get_db), limit: int = 50) -> list[CampaignSummary]:
    rows = db.query(Campaign).order_by(Campaign.created_at.desc()).limit(min(limit, 200)).all()
    return [_summary(c) for c in rows]


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
def get_campaign(campaign_id: str, db: Session = Depends(get_db)) -> CampaignDetail:
    camp = db.get(Campaign, campaign_id)
    if camp is None:
        raise HTTPException(404, "campaign not found")

    cost = float(
        db.query(func.coalesce(func.sum(CostLog.amount_usd), 0.0))
        .filter(CostLog.campaign_id == campaign_id).scalar() or 0.0
    )
    s = get_settings()
    runs = db.query(AgentRun).filter_by(campaign_id=campaign_id).order_by(AgentRun.started_at).all()
    done_step = _STEP_ORDER.get(camp.current_step or "", -1)

    def step_status(name: str) -> str:
        idx = _STEP_ORDER[name]
        if camp.status == "FAILED" and idx == done_step:
            return "FAILED"
        if camp.status == "SUCCESS":
            return "SUCCESS"
        if idx < done_step:
            return "SUCCESS"
        if idx == done_step:
            return "RUNNING" if camp.status == "RUNNING" else "SUCCESS"
        return "WAITING"

    sources = db.query(ResearchSource).filter_by(campaign_id=campaign_id).all()
    facts = db.query(VerifiedFact).filter_by(campaign_id=campaign_id).all()
    strat = db.query(Strategy).filter_by(campaign_id=campaign_id).first()
    hooks = db.query(Hook).filter_by(campaign_id=campaign_id).order_by(Hook.rank).all()
    script = db.query(Script).filter_by(campaign_id=campaign_id).first()

    return CampaignDetail(
        **_summary(camp).model_dump(),
        platforms=camp.platforms or [],
        knowledge_pack=camp.knowledge_pack,
        error_message=camp.error_message,
        steps=[{"name": n, "status": step_status(n)} for n in PIPELINE_STEPS if n != "research_fix" or done_step >= _STEP_ORDER["research_fix"]],
        sources=[{"id": s_.id, "url": s_.url, "title": s_.title, "snippet": s_.snippet,
                  "published_at": s_.published_at} for s_ in sources],
        verified_facts=[{"fact": f.fact, "status": f.status, "confidence": f.confidence,
                         "source_ids": f.source_ids, "reason": f.reason} for f in facts],
        strategy=(
            {"angle": strat.angle, "key_message": strat.key_message, "tone": strat.tone,
             "target_emotion": strat.target_emotion, **(strat.payload or {})}
            if strat else None
        ),
        hooks=[{"text": h.text, "style": h.style, "score": h.score, "rank": h.rank} for h in hooks],
        script=(
            {"platform": script.platform, "body": script.body, "draft_body": script.draft_body,
             "word_count": script.word_count, "qa_passed": script.qa_passed,
             "qa_report": script.qa_report, "cta_type": script.cta_type,
             "ai_slop_score": script.ai_slop_score, "naturalness": script.naturalness}
            if script else None
        ),
        agent_runs=[{"agent_name": r.agent_name, "status": r.status, "provider": r.provider,
                     "model": r.model, "input_tokens": r.input_tokens,
                     "output_tokens": r.output_tokens, "estimated_cost": r.estimated_cost,
                     "error_type": r.error_type, "error_message": r.error_message} for r in runs],
        cost_usd=round(cost, 6),
        budget={"campaign": s.campaign_budget_usd, "daily": s.daily_budget_usd,
                "monthly": s.monthly_budget_usd, "spent_campaign": round(cost, 6)},
    )


@router.post("/campaigns/{campaign_id}/resume", response_model=CampaignSummary)
def resume_campaign(campaign_id: str, db: Session = Depends(get_db)) -> CampaignSummary:
    camp = db.get(Campaign, campaign_id)
    if camp is None:
        raise HTTPException(404, "campaign not found")
    from app.celery_app import celery_app  # noqa: F401
    from app.tasks import run_campaign_task

    args = [camp.id, camp.topic, camp.audience_goal, camp.platforms]
    kw = {"resume": True}
    if get_settings().run_inline:
        run_campaign_task.apply(args=args, kwargs=kw)
    else:
        try:
            run_campaign_task.apply_async(args=args, kwargs=kw)
        except Exception:
            run_campaign_task.apply(args=args, kwargs=kw)
    db.refresh(camp)
    return _summary(camp)


def _task_mentions_campaign(task: dict, campaign_id: str) -> bool:
    """Celery inspect payloads vary by version; match only serialized task args."""
    try:
        return campaign_id in json.dumps(
            {"args": task.get("args"), "kwargs": task.get("kwargs")},
            ensure_ascii=False,
        )
    except (TypeError, ValueError):
        return False


def _revoke_campaign_tasks(campaign_id: str) -> list[str]:
    """Cancel queued tasks and terminate an active render child process."""
    from app.celery_app import celery_app

    revoked: list[str] = []
    try:
        inspector = celery_app.control.inspect(timeout=0.75)
        snapshots = [inspector.active() or {}, inspector.reserved() or {}, inspector.scheduled() or {}]
        for snapshot in snapshots:
            for tasks in snapshot.values():
                for entry in tasks or []:
                    task = entry.get("request", entry)
                    task_id = task.get("id")
                    if task_id and _task_mentions_campaign(task, campaign_id) and task_id not in revoked:
                        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
                        revoked.append(task_id)
    except Exception:  # worker unavailable: DB cancellation still prevents resume/retry
        pass
    return revoked


def _remove_campaign_files(campaign_id: str) -> None:
    settings = get_settings()
    targets = [
        Path(settings.storage_root).resolve() / "campaigns" / campaign_id,
        Path(settings.output_root).resolve() / campaign_id,
    ]
    for target in targets:
        # campaign_id is a DB key, but keep filesystem deletion narrowly contained.
        if target.name == campaign_id and target.is_dir():
            shutil.rmtree(target)


@router.post("/campaigns/{campaign_id}/cancel")
def cancel_campaign(campaign_id: str, db: Session = Depends(get_db)):
    camp = db.get(Campaign, campaign_id)
    if camp is None:
        raise HTTPException(404, "campaign not found")
    if camp.status in {"SUCCESS", "FAILED", "CANCELLED"}:
        return {"ok": True, "campaign_id": campaign_id, "status": camp.status, "revoked_tasks": []}

    # Persist first so a cooperative pipeline sees cancellation even if no worker
    # answers Celery inspect (for example while Docker is restarting).
    camp.status = "CANCELLED"
    camp.current_step = "cancelled"
    camp.error_message = None
    db.query(AgentRun).filter_by(campaign_id=campaign_id, status="RUNNING").update(
        {AgentRun.status: "CANCELLED"}, synchronize_session=False
    )
    db.commit()
    revoked = _revoke_campaign_tasks(campaign_id)
    return {"ok": True, "campaign_id": campaign_id, "status": "CANCELLED", "revoked_tasks": revoked}


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(campaign_id: str, db: Session = Depends(get_db)):
    """Stop work, remove generated files, then remove every campaign DB row."""
    camp = db.get(Campaign, campaign_id)
    if camp is None:
        raise HTTPException(404, "campaign not found")

    _revoke_campaign_tasks(campaign_id)
    _remove_campaign_files(campaign_id)
    deleted = 0
    for table in reversed(Base.metadata.sorted_tables):
        if table.name == Campaign.__tablename__ or "campaign_id" not in table.c:
            continue
        result = db.execute(table.delete().where(table.c.campaign_id == campaign_id))
        deleted += max(0, int(result.rowcount or 0))
    db.delete(camp)
    db.commit()
    return {"ok": True, "campaign_id": campaign_id, "deleted_records": deleted + 1}


def _summary(c: Campaign) -> CampaignSummary:
    return CampaignSummary(
        id=c.id, topic=c.topic, status=c.status, current_step=c.current_step,
        audience_goal=c.audience_goal, fact_score=c.fact_score,
        created_at=c.created_at.isoformat() if c.created_at else "",
    )
