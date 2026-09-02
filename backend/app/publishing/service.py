from __future__ import annotations

from datetime import datetime

from app.config import get_settings
from app.db.models import Asset, Campaign, PlatformContent, PublishAudit, PublishJob
from app.platforms import get_platform
from app.publishing.base import PublishStatus
from app.publishing.capabilities import get_capability
from app.publishing.idempotency import make_idempotency_key, media_hash
from app.publishing.scheduler import schedule_job


def _media_for(session, campaign_id: str, content: PlatformContent) -> tuple[list[str], str | None]:
    spec = get_platform(content.platform)
    q = session.query(Asset).filter_by(campaign_id=campaign_id, content_id=content.id)
    render = q.filter_by(asset_type="render").order_by(Asset.created_at.desc()).first()
    thumb = q.filter_by(asset_type="thumbnail").first()
    if spec.family.value in ("VIDEO", "MIXED") and render:
        return [render.id], (thumb.id if thumb else None)
    imgs = [a.id for a in q.filter(Asset.asset_type.in_(["image", "carousel"]))
            .order_by(Asset.created_at)]
    return imgs, (thumb.id if thumb else None)


def create_jobs_for_campaign(
    session, campaign_id: str, *,
    accounts: dict[str, str] | None = None,
    schedule: dict[str, datetime] | None = None,
    run_mode: str | None = None,
    dry_run: bool | None = None,
) -> list[PublishJob]:
    s = get_settings()
    camp = session.get(Campaign, campaign_id)
    if camp is None:
        raise ValueError("campaign not found")
    accounts = accounts or {}
    schedule = schedule or {}
    run_mode = run_mode or s.publish_mode
    dry_run = s.dry_run if dry_run is None else dry_run

    # Cross-Phase Intelligence Upgrade — LEARN_ONLY / REFERENCE_ONLY never publish
    from app.intel.modes import is_learn_only
    from app.intel.platform_selection import publish_allowed

    if is_learn_only(getattr(camp, "execution_mode", None)):
        return []

    contents = session.query(PlatformContent).filter_by(campaign_id=campaign_id).all()
    jobs: list[PublishJob] = []
    for content in contents:
        cap = get_capability(content.platform)
        # only GENERATE_AND_PUBLISH platforms get a job (spec §AR / §AS)
        _ok, _sel_mode = publish_allowed(session, campaign_id=campaign_id,
                                         platform=content.platform, content_type=content.content_type)
        if not _ok:
            continue
        media_ids, thumb_id = _media_for(session, campaign_id, content)
        asset_hashes = [a.hash for a in session.query(Asset).filter(Asset.id.in_(media_ids))]
        acct_id = accounts.get(content.platform)
        when = schedule.get(content.platform)
        idem = make_idempotency_key(
            platform=content.platform, account_id=acct_id or "none",
            content_id=content.id, scheduled_at=when.isoformat() if when else "asap",
            media_hash_=media_hash(asset_hashes),
        )
        existing = session.query(PublishJob).filter_by(idempotency_key=idem).first()
        if existing:
            jobs.append(existing)
            continue

        job = PublishJob(
            campaign_id=campaign_id, content_id=content.id, platform=content.platform,
            platform_account_id=acct_id, content_type=content.content_type,
            title=content.title or camp.topic, description=content.script,
            caption=content.caption or content.hook, hashtags=content.hashtags or [],
            media_asset_ids=media_ids, thumbnail_asset_id=thumb_id,
            privacy="PRIVATE", platform_settings={"cta": content.cta},
            ai_generated=True, run_mode=run_mode, max_attempts=s.publish_max_attempts,
            idempotency_key=idem, dry_run=dry_run,
            approval_status="APPROVED" if run_mode == "MANUAL" else "PENDING",
            platform_selection_mode=_sel_mode,
        )
        if not cap.auto_publish_possible:
            job.status = (PublishStatus.NOT_SUPPORTED.value
                          if cap.publishing_status == "NOT_SUPPORTED"
                          else PublishStatus.WAITING_USER_ACTION.value
                          if cap.publishing_status == "MANUAL_ONLY"
                          else PublishStatus.WAITING_PLATFORM_ACTION.value)
        elif when is not None:
            pass  # scheduled below
        else:
            job.status = PublishStatus.READY.value
        session.add(job)
        session.flush()
        if when is not None and cap.auto_publish_possible:
            schedule_job(session, job, when, content.payload.get("timezone", s.publish_default_timezone)
                         if content.payload else s.publish_default_timezone)
        session.add(PublishAudit(publish_job_id=job.id, campaign_id=campaign_id, action="job_created",
                                 run_mode=run_mode, platform=content.platform,
                                 payload={"idempotency_key": idem, "dry_run": dry_run}))
        jobs.append(job)
    session.flush()
    return jobs


def approve_job(session, job_id: str, actor: str) -> PublishJob:
    job = session.get(PublishJob, job_id)
    if job is None:
        raise ValueError("job not found")
    job.approval_status = "APPROVED"
    job.approved_by = actor
    if job.status in (PublishStatus.DRAFT.value, PublishStatus.WAITING_APPROVAL.value):
        job.status = PublishStatus.READY.value
    session.add(PublishAudit(publish_job_id=job.id, campaign_id=job.campaign_id,
                             action="job_approved", run_mode=job.run_mode,
                             platform=job.platform, payload={"actor": actor}))
    session.flush()
    return job


def campaign_rollup(session, campaign_id: str) -> str:
    jobs = session.query(PublishJob).filter_by(campaign_id=campaign_id).all()
    auto = [j for j in jobs if get_capability(j.platform).auto_publish_possible]
    if not auto:
        return "NO_AUTO_TARGETS"
    published = [j for j in auto if j.status == PublishStatus.PUBLISHED.value]
    failed = [j for j in auto if j.status in (PublishStatus.FAILED.value, PublishStatus.BLOCKED.value)]
    if len(published) == len(auto):
        return "ALL_PUBLISHED"
    if published:
        return "PARTIALLY_PUBLISHED"
    if failed:
        return "FAILED"
    return "IN_PROGRESS"
