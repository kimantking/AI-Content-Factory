"""Cross-Phase Intelligence Upgrade API — references / learning / datasets /
skills / prompts / recipes / platform selection / one-screen campaign compose.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import get_db
from app.db.models import Campaign
from app.db.models_learn import (
    CreativeRecipe,
    DatasetRecord,
    LearnedSkillNote,
    LearningCollection,
    LearningJob,
    PromptBlueprint,
    ReferenceAnalysis,
    ReferenceSource,
)
from app.intel import distillation
from app.intel.engine import LearningGuardError, add_urls, run_learning_job
from app.intel.gap import detect_gaps
from app.intel.modes import is_learn_only, resolve_execution_mode
from app.intel.platform_selection import (
    BUILTIN_PRESETS,
    CONTENT_TYPES,
    apply_preset,
    cost_preview,
    resolve_selection,
    set_selection,
)

router = APIRouter(prefix="/api", tags=["intel"])


def _ref_out(r: ReferenceSource) -> dict:
    return {
        "id": r.id, "url": r.url, "canonical_url": r.canonical_url,
        "source_type": r.source_type, "support_level": r.support_level,
        "purpose": r.purpose, "resolved_purpose": r.resolved_purpose, "scope": r.scope,
        "status": r.status, "title": r.title, "publisher": r.publisher,
        "quality_score": r.quality_score, "trust_score": r.trust_score,
        "relevance_score": r.relevance_score, "freshness_score": r.freshness_score,
        "learning_weight": r.learning_weight, "rights_status": r.rights_status,
        "injection_flag": r.injection_flag, "injection_detail": r.injection_detail,
        "language": r.language, "topic_cluster": r.topic_cluster, "error": r.error,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# --------------------------------------------------------------------- #
#  references + learning jobs
# --------------------------------------------------------------------- #

@router.post("/references", status_code=201)
def add_references(payload: dict = Body(...), db: Session = Depends(get_db)):
    urls = payload.get("urls") or ([payload["url"]] if payload.get("url") else [])
    if not urls:
        raise HTTPException(400, "urls required")
    execution_mode = payload.get("execution_mode", "REFERENCE_ONLY")
    scope = "WORKSPACE" if execution_mode == "LEARN_ONLY" else payload.get("scope", "WORKSPACE")
    try:
        job = add_urls(
            db, urls=urls,
            execution_mode=execution_mode,
            scope=scope,
            workspace_id=payload.get("workspace_id"), brand_id=payload.get("brand_id"),
            channel_id=payload.get("channel_id"), campaign_id=payload.get("campaign_id"),
            collection_id=payload.get("collection_id"),
            purpose=payload.get("purpose", "AUTO"), topic=payload.get("topic", ""),
            video_profiles=payload.get("video_profiles"),
        )
    except LearningGuardError as e:
        raise HTTPException(429, str(e))
    db.commit()
    if payload.get("run", True):
        run_learning_job(db, job.id)
        db.commit()
    job = db.get(LearningJob, job.id)
    return {"job_id": job.id, "status": job.status, "result": job.result,
            "references": [_ref_out(r) for r in
                           db.query(ReferenceSource).filter_by(learning_job_id=job.id).all()]}


@router.post("/references/analyze")
def analyze_job(payload: dict = Body(...), db: Session = Depends(get_db)):
    job_id = payload.get("job_id")
    job = db.get(LearningJob, job_id) if job_id else None
    if job is None:
        raise HTTPException(404, "job not found")
    res = run_learning_job(db, job.id)
    db.commit()
    return res


@router.get("/references")
def list_references(workspace_id: str | None = None, status: str | None = None,
                    limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(ReferenceSource)
    if workspace_id:
        q = q.filter(ReferenceSource.workspace_id == workspace_id)
    if status:
        q = q.filter(ReferenceSource.status == status)
    rows = q.order_by(ReferenceSource.created_at.desc()).limit(min(limit, 500)).all()
    return [_ref_out(r) for r in rows]


@router.get("/references/{reference_id}")
def get_reference(reference_id: str, db: Session = Depends(get_db)):
    r = db.get(ReferenceSource, reference_id)
    if r is None:
        raise HTTPException(404, "not found")
    analyses = {a.analysis_kind: {"data": a.data, "confidence": a.confidence,
                                  "unknown_fields": a.unknown_fields}
                for a in db.query(ReferenceAnalysis).filter_by(reference_id=reference_id).all()}
    return {**_ref_out(r), "analyses": analyses}


@router.post("/references/retry-failed")
def retry_failed_references(payload: dict = Body(default={}), db: Session = Depends(get_db)):
    """Retry previously failed fetches after connectivity/configuration is fixed."""
    q = db.query(ReferenceSource).filter(ReferenceSource.status == "FETCH_FAILED")
    workspace_id = payload.get("workspace_id")
    if workspace_id:
        q = q.filter(ReferenceSource.workspace_id == workspace_id)
    failed = q.all()
    if not failed:
        return {"ok": True, "retried": 0, "ready": 0, "failed": 0, "jobs": []}

    job_ids = sorted({r.learning_job_id for r in failed if r.learning_job_id})
    for ref in failed:
        ref.status = "PENDING"
        ref.error = ""
    db.flush()

    results = [run_learning_job(db, job_id) for job_id in job_ids]
    db.commit()
    refreshed = db.query(ReferenceSource).filter(ReferenceSource.id.in_([r.id for r in failed])).all()
    return {
        "ok": True,
        "retried": len(refreshed),
        "ready": sum(r.status == "READY" for r in refreshed),
        "failed": sum(r.status == "FETCH_FAILED" for r in refreshed),
        "jobs": results,
    }


@router.get("/learning")
def learning_dashboard(workspace_id: str | None = None, db: Session = Depends(get_db)):
    def _c(model, **f):
        q = db.query(model)
        if workspace_id:
            q = q.filter(model.workspace_id == workspace_id)
        for k, v in f.items():
            q = q.filter(getattr(model, k) == v)
        return q.count()

    last = db.query(LearningJob)
    if workspace_id:
        last = last.filter(LearningJob.workspace_id == workspace_id)
    last = last.order_by(LearningJob.created_at.desc()).first()
    refs = db.query(ReferenceSource)
    if workspace_id:
        refs = refs.filter(ReferenceSource.workspace_id == workspace_id)
    refs = refs.all()
    video_refs = sum(1 for r in refs if r.resolved_purpose == "VIDEO_REFERENCE")
    writing_refs = sum(1 for r in refs if r.resolved_purpose == "STYLE_REFERENCE")
    return {
        "total_references": len(refs),
        "ready_references": sum(1 for r in refs if r.status == "READY"),
        "dataset_records": _c(DatasetRecord),
        "video_references": video_refs,
        "writing_references": writing_refs,
        "prompt_blueprints": _c(PromptBlueprint),
        "learned_skills": _c(LearnedSkillNote),
        "creative_recipes": _c(CreativeRecipe),
        "collections": _c(LearningCollection),
        "learning_cost_usd": round(sum(j.cost_usd for j in (
            db.query(LearningJob).filter(LearningJob.workspace_id == workspace_id).all()
            if workspace_id else db.query(LearningJob).all())), 4),
        "last_learning_run": last.created_at.isoformat() if last and last.created_at else None,
    }


@router.get("/learning/jobs")
def list_jobs(workspace_id: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(LearningJob)
    if workspace_id:
        q = q.filter(LearningJob.workspace_id == workspace_id)
    return [{"id": j.id, "execution_mode": j.execution_mode, "status": j.status,
             "total_urls": j.total_urls, "ready": j.ready, "blocked": j.blocked,
             "duplicates": j.duplicates, "datasets_written": j.datasets_written,
             "blueprints_created": j.blueprints_created, "skills_created": j.skills_created,
             "created_at": j.created_at.isoformat() if j.created_at else None}
            for j in q.order_by(LearningJob.created_at.desc()).limit(min(limit, 200)).all()]


@router.get("/learning/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    j = db.get(LearningJob, job_id)
    if j is None:
        raise HTTPException(404, "not found")
    return {"id": j.id, "execution_mode": j.execution_mode, "status": j.status,
            "result": j.result, "config_snapshot": j.config_snapshot,
            "references": [_ref_out(r) for r in
                           db.query(ReferenceSource).filter_by(learning_job_id=j.id).all()]}


# --------------------------------------------------------------------- #
#  collections / datasets / skills / prompts / recipes / gaps
# --------------------------------------------------------------------- #

@router.get("/learning/collections")
def list_collections(workspace_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(LearningCollection)
    if workspace_id:
        q = q.filter(LearningCollection.workspace_id == workspace_id)
    return [{"id": c.id, "name": c.name, "description": c.description,
             "default_purpose": c.default_purpose, "default_scope": c.default_scope,
             "reference_count": c.reference_count} for c in q.all()]


@router.post("/learning/collections", status_code=201)
def create_collection(payload: dict = Body(...), db: Session = Depends(get_db)):
    c = LearningCollection(
        workspace_id=payload.get("workspace_id"), brand_id=payload.get("brand_id"),
        channel_id=payload.get("channel_id"), name=payload["name"][:160],
        description=payload.get("description", ""),
        default_purpose=payload.get("default_purpose", "AUTO"),
        default_scope=payload.get("default_scope", "CHANNEL"),
        watchlist=payload.get("watchlist", {}))
    db.add(c)
    db.commit()
    return {"id": c.id, "name": c.name}


@router.get("/learning/datasets")
def list_datasets(workspace_id: str | None = None, dataset_type: str | None = None,
                  active: bool = True, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(DatasetRecord)
    if workspace_id:
        q = q.filter(DatasetRecord.workspace_id == workspace_id)
    if dataset_type:
        q = q.filter(DatasetRecord.dataset_type == dataset_type)
    q = q.filter(DatasetRecord.active.is_(active))
    return [{"id": r.id, "dataset_type": r.dataset_type, "reference_id": r.reference_id,
             "quality_score": r.quality_score, "learning_weight": r.learning_weight,
             "curator_flags": r.curator_flags, "topic_cluster": r.topic_cluster,
             "rights_status": r.rights_status}
            for r in q.order_by(DatasetRecord.learning_weight.desc()).limit(min(limit, 500)).all()]


@router.get("/learning/skills")
def list_skills(workspace_id: str | None = None, agent_type: str | None = None,
                db: Session = Depends(get_db)):
    q = db.query(LearnedSkillNote)
    if workspace_id:
        q = q.filter(LearnedSkillNote.workspace_id == workspace_id)
    if agent_type:
        q = q.filter(LearnedSkillNote.agent_type == agent_type)
    return [{"id": n.id, "agent_type": n.agent_type, "skill_category": n.skill_category,
             "rule": n.rule, "confidence": n.confidence, "sample_size": n.sample_size,
             "status": n.status, "evidence_ids": n.evidence_ids,
             "platform": n.platform, "content_type": n.content_type}
            for n in q.order_by(LearnedSkillNote.confidence.desc()).limit(300).all()]


@router.get("/learning/prompts")
def list_prompts(workspace_id: str | None = None, agent_type: str | None = None,
                 db: Session = Depends(get_db)):
    q = db.query(PromptBlueprint)
    if workspace_id:
        q = q.filter(PromptBlueprint.workspace_id == workspace_id)
    if agent_type:
        q = q.filter(PromptBlueprint.agent_type == agent_type)
    return [_bp_out(b) for b in q.order_by(PromptBlueprint.confidence.desc()).limit(300).all()]


def _bp_out(b: PromptBlueprint) -> dict:
    return {"id": b.id, "agent_type": b.agent_type, "purpose": b.purpose,
            "instructions": b.instructions, "constraints": b.constraints,
            "positive_patterns": b.positive_patterns, "negative_patterns": b.negative_patterns,
            "status": b.status, "version": b.version, "confidence": b.confidence,
            "sample_size": b.sample_size, "source_diversity": b.source_diversity,
            "consistency": b.consistency, "platforms": b.platforms,
            "content_types": b.content_types}


@router.get("/learning/prompts/{blueprint_id}")
def get_prompt(blueprint_id: str, db: Session = Depends(get_db)):
    b = db.get(PromptBlueprint, blueprint_id)
    if b is None:
        raise HTTPException(404, "not found")
    from app.db.models_learn import PromptBlueprintEvidence
    ev = [{"evidence_type": e.evidence_type, "reference_id": e.reference_id,
           "campaign_id": e.campaign_id, "observation": e.observation, "weight": e.weight,
           "metric_delta": e.metric_delta}
          for e in db.query(PromptBlueprintEvidence).filter_by(blueprint_id=blueprint_id).all()]
    return {**_bp_out(b), "evidence": ev}


@router.post("/learning/prompts/{blueprint_id}/test")
def test_prompt(blueprint_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db)):
    from app.intel.composer import compose

    b = db.get(PromptBlueprint, blueprint_id)
    if b is None:
        raise HTTPException(404, "not found")
    out = compose(db, agent_type=b.agent_type, base_prompt=payload.get("base_prompt", "(base agent prompt)"),
                  workspace_id=b.workspace_id, platform=payload.get("platform"),
                  content_type=payload.get("content_type"), include_experimental=True)
    return {"blueprint": _bp_out(b), "preview_prompt": out["prompt"],
            "used_skills": out["used_skills"], "used_blueprints": out["used_blueprints"],
            "truncated": out["truncated"]}


@router.post("/learning/prompts/{blueprint_id}/promote")
def promote_prompt(blueprint_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db)):
    to = payload.get("to_status", "PROMOTED").upper()
    res = distillation.advance_status(db, blueprint_id, to, actor=payload.get("actor", "user"),
                                      reason=payload.get("reason", ""))
    db.commit()
    if not res["ok"]:
        raise HTTPException(409, res["error"])
    return res


@router.post("/learning/prompts/{blueprint_id}/rollback")
def rollback_prompt(blueprint_id: str, db: Session = Depends(get_db)):
    res = distillation.rollback(db, blueprint_id, actor="user")
    db.commit()
    if not res["ok"]:
        raise HTTPException(404, res["error"])
    return res


@router.get("/learning/recipes")
def list_recipes(workspace_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(CreativeRecipe)
    if workspace_id:
        q = q.filter(CreativeRecipe.workspace_id == workspace_id)
    return [{"id": r.id, "name": r.name, "platform": r.platform, "content_type": r.content_type,
             "confidence": r.confidence, "evidence_ids": r.evidence_ids, "status": r.status}
            for r in q.all()]


@router.get("/learning/gaps")
def learning_gaps(workspace_id: str | None = None, db: Session = Depends(get_db)):
    return detect_gaps(db, workspace_id=workspace_id)


# --------------------------------------------------------------------- #
#  platform selection
# --------------------------------------------------------------------- #

@router.get("/platform-selection/content-types")
def platform_content_types():
    return {"content_types": CONTENT_TYPES, "presets": list(BUILTIN_PRESETS)}


@router.post("/platform-selection")
def post_platform_selection(payload: dict = Body(...), db: Session = Depends(get_db)):
    cid = payload.get("campaign_id")
    camp = db.get(Campaign, cid) if cid else None
    if camp is None:
        raise HTTPException(404, "campaign not found")
    sel = payload.get("selection")
    if payload.get("preset"):
        sel = apply_preset(payload["preset"], db, workspace_id=camp.workspace_id)
    res = set_selection(db, campaign_id=cid, selection=sel or {},
                        workspace_id=camp.workspace_id, brand_id=camp.brand_id,
                        channel_id=camp.channel_id,
                        source=payload.get("source", "USER"),
                        user_explicit=payload.get("user_explicit", True))
    db.commit()
    return {**res, "cost_preview": cost_preview(db, campaign_id=cid)}


@router.get("/platform-selection/{campaign_id}")
def get_platform_selection(campaign_id: str, db: Session = Depends(get_db)):
    if db.get(Campaign, campaign_id) is None:
        raise HTTPException(404, "campaign not found")
    return {"campaign_id": campaign_id, "selection": resolve_selection(db, campaign_id),
            "cost_preview": cost_preview(db, campaign_id=campaign_id)}


@router.get("/platform-presets")
def list_presets(workspace_id: str | None = None, db: Session = Depends(get_db)):
    from app.db.models_learn import PlatformPreset
    q = db.query(PlatformPreset)
    if workspace_id:
        q = q.filter(PlatformPreset.workspace_id == workspace_id)
    custom = [{"id": p.id, "name": p.name, "builtin": False, "selection": p.selection}
              for p in q.all()]
    builtin = [{"id": f"builtin:{k}", "name": k, "builtin": True, "selection": v}
               for k, v in BUILTIN_PRESETS.items()]
    return builtin + custom


@router.post("/platform-presets", status_code=201)
def create_preset(payload: dict = Body(...), db: Session = Depends(get_db)):
    from app.db.models_learn import PlatformPreset
    from app.intel.platform_selection import normalize_selection

    p = PlatformPreset(workspace_id=payload.get("workspace_id"), brand_id=payload.get("brand_id"),
                       channel_id=payload.get("channel_id"), name=payload["name"][:120],
                       selection=normalize_selection(payload.get("selection", {})))
    db.add(p)
    db.commit()
    return {"id": p.id, "name": p.name}


# --------------------------------------------------------------------- #
#  one-screen compose (spec §A / §BC)
# --------------------------------------------------------------------- #

@router.post("/campaigns/compose", status_code=201)
def compose_campaign(payload: dict = Body(...), db: Session = Depends(get_db)):
    s = get_settings()
    mode = resolve_execution_mode(payload.get("execution_mode", "CREATE_AND_LEARN"))
    topic = (payload.get("topic") or "").strip()
    urls = payload.get("reference_urls") or []
    ws = payload.get("workspace_id")
    br = payload.get("brand_id")
    ch = payload.get("channel_id")

    if not is_learn_only(mode) and not topic:
        raise HTTPException(400, "topic is required unless execution_mode is LEARN_ONLY / REFERENCE_ONLY")

    campaign_id = None
    if not is_learn_only(mode):
        camp = Campaign(topic=topic, audience_goal=(payload.get("audience_goal") or "BALANCED").upper(),
                        platforms=[], status="WAITING", workspace_id=ws, brand_id=br, channel_id=ch,
                        execution_mode=mode.value)
        db.add(camp)
        db.flush()
        campaign_id = camp.id
        sel = payload.get("platform_selection")
        if payload.get("preset"):
            sel = apply_preset(payload["preset"], db, workspace_id=ws)
        set_selection(db, campaign_id=campaign_id, selection=sel or {}, workspace_id=ws,
                      brand_id=br, channel_id=ch, source="USER", user_explicit=True)

    learning = {"job_id": None}
    if urls and mode.value != "CREATE_ONLY":
        try:
            job = add_urls(db, urls=urls, execution_mode=mode.value,
                           scope="WORKSPACE",
                           workspace_id=ws, brand_id=br, channel_id=ch,
                           campaign_id=campaign_id, purpose=payload.get("purpose", "AUTO"),
                           topic=topic, video_profiles=payload.get("video_profiles"))
        except LearningGuardError as e:
            raise HTTPException(429, str(e))
        db.flush()
        res = run_learning_job(db, job.id)
        learning = {"job_id": job.id, **res}

    db.commit()

    started = False
    if campaign_id and not is_learn_only(mode):
        camp = db.get(Campaign, campaign_id)
        if camp.platforms:
            from app.api.routes_campaigns import _enqueue
            _enqueue(camp)
            started = True
            db.refresh(camp)

    return {
        "execution_mode": mode.value,
        "campaign_id": campaign_id,
        "pipeline_started": started,
        "generate_platforms": (db.get(Campaign, campaign_id).platforms if campaign_id else []),
        "learning": learning,
    }
