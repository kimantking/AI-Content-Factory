from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import get_db
from app.db.models import (
    Campaign,
    PlatformAccount,
    PublicationEvent,
    PublishJob,
)
from app.publishing import load_capabilities
from app.publishing.crypto import encrypt_token, mask_token
from app.publishing.oauth import complete_authorization, start_authorization
from app.publishing.scheduler import reschedule
from app.publishing.service import approve_job, campaign_rollup, create_jobs_for_campaign
from app.publishing.token_manager import health_check
from app.publishing.webhooks import apply_webhook, verify_signature

router = APIRouter(prefix="/api/publishing", tags=["publishing"])
wh_router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class ConnectMockRequest(BaseModel):
    account_name: str = "Mock Account"
    account_type: str = "BUSINESS"


class CreateJobsRequest(BaseModel):
    accounts: dict[str, str] = {}
    schedule: dict[str, datetime] = {}
    run_mode: str | None = None
    dry_run: bool | None = None


class JobPatch(BaseModel):
    title: str | None = None
    caption: str | None = None
    description: str | None = None
    hashtags: list[str] | None = None
    privacy: str | None = None


# ---- capabilities ------------------------------------------------------- #

@router.get("/capabilities")
def capabilities():
    return [c.__dict__ for c in load_capabilities().values()]


# ---- accounts / OAuth ------------------------------------------------- #

@router.post("/accounts/{platform}/connect")
def connect(platform: str, db: Session = Depends(get_db)):
    try:
        return start_authorization(db, platform)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)) from e


@router.get("/oauth/{platform}/callback")
def oauth_callback(platform: str, state: str, code: str, db: Session = Depends(get_db)):
    bundle = complete_authorization(db, platform, state, code)
    acct = (db.query(PlatformAccount)
            .filter_by(platform=platform, account_id=bundle["account_id"]).first())
    if acct is None:
        acct = PlatformAccount(platform=platform, account_id=bundle["account_id"])
        db.add(acct)
    acct.account_name = bundle["account_name"]
    acct.account_type = "BUSINESS"
    acct.scopes = bundle["scopes"]
    acct.access_token_encrypted = encrypt_token(bundle["access_token"])
    acct.refresh_token_encrypted = encrypt_token(bundle.get("refresh_token"))
    acct.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=bundle.get("expires_in", 3600))
    acct.connection_status = "CONNECTED"
    acct.integration_status = "REAL_AUTH_TESTED" if bundle["provider_mode"] == "REAL" else "MOCK_TESTED"
    db.commit()
    db.refresh(acct)
    return {"connected": True, "account_id": acct.id, "provider_mode": bundle["provider_mode"]}


@router.post("/accounts/{platform}/mock-connect")
def mock_connect(platform: str, payload: ConnectMockRequest, db: Session = Depends(get_db)):
    """Dev/test helper: create a CONNECTED mock account without the redirect dance."""
    if not get_settings().mock_mode:
        raise HTTPException(403, "실사용 모드에서는 Mock 계정을 연결할 수 없습니다.")
    from app.publishing.capabilities import get_capability

    cap = get_capability(platform)
    acct = PlatformAccount(
        platform=platform, account_id=f"mock-{platform}", account_name=payload.account_name,
        account_type=payload.account_type, scopes=list(cap.required_scopes),
        access_token_encrypted=encrypt_token(f"mock-access-{platform}"),
        refresh_token_encrypted=encrypt_token(f"mock-refresh-{platform}"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        connection_status="CONNECTED", integration_status="MOCK_TESTED",
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return {"account_id": acct.id, "connection_status": acct.connection_status}


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    out = []
    for a in db.query(PlatformAccount).order_by(PlatformAccount.platform):
        h = health_check(db, a)
        out.append({
            "id": a.id, **h,
            "access_token": mask_token("mock-access") if a.access_token_encrypted else None,
        })
    db.commit()
    return out


@router.post("/accounts/{account_id}/test")
def test_account(account_id: str, db: Session = Depends(get_db)):
    a = db.get(PlatformAccount, account_id)
    if a is None:
        raise HTTPException(404, "account not found")
    h = health_check(db, a)
    db.commit()
    return h


@router.post("/accounts/{account_id}/disconnect")
def disconnect(account_id: str, db: Session = Depends(get_db)):
    a = db.get(PlatformAccount, account_id)
    if a is None:
        raise HTTPException(404, "account not found")
    a.access_token_encrypted = None
    a.refresh_token_encrypted = None
    a.connection_status = "DISCONNECTED"
    db.commit()
    return {"disconnected": True}


# ---- publish jobs -------------------------------------------------- #

@router.post("/campaigns/{campaign_id}/jobs", status_code=201)
def create_jobs(campaign_id: str, payload: CreateJobsRequest, db: Session = Depends(get_db)):
    if db.get(Campaign, campaign_id) is None:
        raise HTTPException(404, "campaign not found")
    jobs = create_jobs_for_campaign(
        db, campaign_id, accounts=payload.accounts, schedule=payload.schedule,
        run_mode=payload.run_mode, dry_run=payload.dry_run,
    )
    db.commit()
    return [_job_dict(j) for j in jobs]


@router.get("/campaigns/{campaign_id}")
def publishing_dashboard(campaign_id: str, db: Session = Depends(get_db)):
    jobs = db.query(PublishJob).filter_by(campaign_id=campaign_id).order_by(PublishJob.platform).all()
    return {
        "campaign_id": campaign_id,
        "rollup": campaign_rollup(db, campaign_id),
        "dry_run": get_settings().dry_run,
        "publish_mode": get_settings().publish_mode,
        "jobs": [_job_dict(j) for j in jobs],
    }


@router.patch("/jobs/{job_id}")
def patch_job(job_id: str, patch: JobPatch, db: Session = Depends(get_db)):
    j = db.get(PublishJob, job_id)
    if j is None:
        raise HTTPException(404, "job not found")
    if j.status in ("PUBLISHED", "PUBLISHING", "VERIFYING", "UPLOADING", "PROCESSING"):
        raise HTTPException(409, f"job is {j.status}; cannot edit")
    for k, v in patch.model_dump(exclude_none=True).items():
        setattr(j, k, v)
    db.commit()
    return _job_dict(j)


@router.post("/jobs/{job_id}/approve")
def approve(job_id: str, actor: str = Body("dashboard-user", embed=True), db: Session = Depends(get_db)):
    try:
        j = approve_job(db, job_id, actor)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    db.commit()
    return _job_dict(j)


@router.post("/jobs/{job_id}/reschedule")
def reschedule_job(job_id: str, when: datetime = Body(..., embed=True),
                   tz: str | None = Body(None, embed=True), db: Session = Depends(get_db)):
    j = db.get(PublishJob, job_id)
    if j is None:
        raise HTTPException(404, "job not found")
    reschedule(db, j, when, tz)
    db.commit()
    return _job_dict(j)


@router.post("/jobs/{job_id}/run")
def run_job(job_id: str, db: Session = Depends(get_db)):
    if db.get(PublishJob, job_id) is None:
        raise HTTPException(404, "job not found")
    s = get_settings()
    from app.celery_app import celery_app  # noqa: F401
    from app.tasks import run_publish_job_task

    if s.run_inline:
        res = run_publish_job_task.apply(args=[job_id]).get()
        return res
    try:
        run_publish_job_task.apply_async(args=[job_id], queue="publish")
    except Exception:
        return run_publish_job_task.apply(args=[job_id]).get()
    return {"job_id": job_id, "state": "queued"}


@router.get("/jobs/{job_id}/events")
def job_events(job_id: str, db: Session = Depends(get_db)):
    evs = (db.query(PublicationEvent).filter_by(publish_job_id=job_id)
           .order_by(PublicationEvent.created_at).all())
    return [{"event": e.event, "detail": e.detail, "at": e.created_at.isoformat()} for e in evs]


@router.get("/calendar")
def calendar(db: Session = Depends(get_db), days: int = 30):
    now = datetime.now(timezone.utc)
    jobs = (db.query(PublishJob)
            .filter(PublishJob.scheduled_at.isnot(None),
                    PublishJob.scheduled_at <= now + timedelta(days=days))
            .order_by(PublishJob.scheduled_at).all())
    return [{"job_id": j.id, "platform": j.platform, "campaign_id": j.campaign_id,
             "scheduled_at": j.scheduled_at.isoformat() if j.scheduled_at else None,
             "timezone": j.timezone, "status": j.status, "title": j.title} for j in jobs]


@router.get("/calendar/capacity")
def calendar_capacity(workspace_id: str | None = None, db: Session = Depends(get_db)):
    """AUDIT-P6-001 — per-channel daily production capacity (slots + budget
    headroom) + the aggregate the Autopilot controller uses to cap a run."""
    from app.autopilot.capacity import portfolio_capacity
    from app.config import get_settings

    return portfolio_capacity(db, workspace_id=workspace_id,
                              fallback_max=get_settings().autopilot_daily_content_max)


def _job_dict(j: PublishJob) -> dict:
    return {
        "id": j.id, "campaign_id": j.campaign_id, "platform": j.platform,
        "content_type": j.content_type, "status": j.status, "run_mode": j.run_mode,
        "approval_status": j.approval_status, "dry_run": j.dry_run,
        "scheduled_at": j.scheduled_at.isoformat() if j.scheduled_at else None,
        "timezone": j.timezone, "attempt_count": j.attempt_count,
        "idempotency_key": j.idempotency_key,
        "remote_post_id": j.remote_post_id, "remote_url": j.remote_url,
        "last_error_type": j.last_error_type, "dead_lettered": j.dead_lettered,
        "title": j.title, "caption": j.caption, "hashtags": j.hashtags,
    }


# ---- webhooks ---------------------------------------------------- #

@wh_router.post("/{platform}")
async def receive_webhook(platform: str, request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    sig = request.headers.get("x-hub-signature-256") or request.headers.get("x-signature")
    verified = verify_signature(raw, sig)
    import json

    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        payload = {}
    result = apply_webhook(db, platform, payload, verified=verified)
    db.commit()
    if not result["accepted"]:
        raise HTTPException(401, result["reason"])
    return result
