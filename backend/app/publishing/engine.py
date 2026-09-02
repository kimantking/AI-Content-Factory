from __future__ import annotations

from datetime import datetime, timezone

from app.config import get_settings
from app.db.base import session_scope
from app.db.models import (
    Asset,
    Campaign,
    PlatformAccount,
    Publication,
    PublicationEvent,
    PublishAudit,
    PublishJob,
)
from app.publishing.base import (
    ACTIVE_OR_DONE,
    MediaRef,
    PublishError,
    PublishErrorType,
    PublishRequest,
    PublishResult,
    PublishStatus,
)
from app.publishing.capabilities import get_capability
from app.publishing.normalizer import normalize_asset
from app.publishing.polling import PollingManager
from app.publishing.preflight import run_preflight
from app.publishing.publishers import get_publisher
from app.publishing.reconcile import reconcile_job
from app.publishing import retry as retry_mod
from app.publishing.token_manager import ensure_valid
from app.publishing.verify import verify_published


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event(session, job_id: str, event: str, detail: dict | None = None,
           publication_id: str | None = None) -> None:
    session.add(PublicationEvent(publish_job_id=job_id, publication_id=publication_id,
                                 event=event, detail=detail or {}))
    session.flush()


def _audit(session, job: PublishJob, action: str, payload: dict | None = None) -> None:
    session.add(PublishAudit(
        publish_job_id=job.id, campaign_id=job.campaign_id, actor=job.approved_by or "system",
        action=action, run_mode=job.run_mode, platform=job.platform, payload=payload or {},
    ))
    session.flush()


def _upsert_publication(session, job: PublishJob, **fields) -> Publication:
    pub = session.query(Publication).filter_by(publish_job_id=job.id).first()
    if pub is None:
        pub = Publication(publish_job_id=job.id, campaign_id=job.campaign_id,
                          content_id=job.content_id, platform=job.platform,
                          platform_account_id=job.platform_account_id)
        session.add(pub)
    for k, v in fields.items():
        setattr(pub, k, v)
    pub.attempt_count = job.attempt_count
    session.flush()
    return pub


def _schedule_analytics(session, job: PublishJob) -> None:
    """On PUBLISHED: build the content feature vector and queue analytics
    collection windows. Advisory — a failure here never fails the publish."""
    try:
        from app.analytics.feature_store import build_features
        from app.analytics.schedule import create_jobs_for_publication

        pub = _upsert_publication(session, job)
        if job.content_id:
            build_features(session, job.content_id)
        create_jobs_for_publication(session, pub, job.content_type or "SHORT_VIDEO")
    except Exception as e:  # noqa: BLE001
        _event(session, job.id, "ANALYTICS_SCHEDULE_SKIPPED", {"error": str(e)[:300]})


def _build_request(session, job: PublishJob) -> PublishRequest:
    media: list[MediaRef] = []
    for aid in job.media_asset_ids or []:
        a = session.get(Asset, aid)
        if not a:
            continue
        kind = ("video" if (a.asset_type in ("render", "video") or a.mime_type.startswith("video"))
                else "image")
        media.append(MediaRef(asset_id=a.id, path=a.storage_path, mime_type=a.mime_type,
                              width=a.width, height=a.height, duration=a.duration, kind=kind))
    thumb = None
    if job.thumbnail_asset_id:
        ta = session.get(Asset, job.thumbnail_asset_id)
        if ta:
            thumb = MediaRef(asset_id=ta.id, path=ta.storage_path, mime_type=ta.mime_type, kind="thumbnail")
    return PublishRequest(
        job_id=job.id, platform=job.platform, account_id=job.platform_account_id or "",
        content_type=job.content_type, title=job.title, description=job.description,
        caption=job.caption, hashtags=job.hashtags or [], privacy=job.privacy,
        media=media, thumbnail=thumb, platform_settings=job.platform_settings or {},
        ai_generated=job.ai_generated, idempotency_key=job.idempotency_key,
        dry_run=job.dry_run or get_settings().dry_run,
    )


def _finalize_error(session, job: PublishJob, exc: PublishError) -> str:
    job.attempt_count += 1
    job.last_error_type = exc.error_type.value
    job.last_error_message = str(exc)[:2000]
    decision = retry_mod.plan(exc.error_type, attempt=job.attempt_count,
                              max_attempts=job.max_attempts, retry_after=exc.retry_after)
    action = decision["action"]
    if action == "REAUTH_REQUIRED":
        job.status = PublishStatus.REAUTH_REQUIRED.value
    elif action in ("BLOCK", "BLOCKED"):
        job.status = PublishStatus.BLOCKED.value
    elif action == "DO_NOT_REPOST":
        job.status = PublishStatus.FAILED.value
        job.dead_lettered = True
    elif decision["dead_letter"] or action == "DEAD_LETTER":
        job.status = PublishStatus.FAILED.value
        job.dead_lettered = True
    else:
        job.status = PublishStatus.RETRY.value
        job.next_retry_at = decision["next_retry_at"]
    _event(session, job.id, f"ERROR_{exc.error_type.value}",
           {"action": action, "attempt": job.attempt_count})
    _audit(session, job, "publish_error", {"error": exc.error_type.value, "action": action})
    _upsert_publication(session, job, status=job.status, error_code=exc.error_type.value,
                        error_message=str(exc)[:2000])
    return job.status


def run_publish_job(job_id: str) -> dict:
    """Drive ONE PublishJob through preflight → publish → poll → verify.
    Failure here never touches sibling jobs (platform failure isolation)."""
    s = get_settings()
    with session_scope() as session:
        job = session.get(PublishJob, job_id)
        if job is None:
            return {"job_id": job_id, "status": "MISSING"}

        # --- idempotency: already in-flight / done ---
        if PublishStatus(job.status) in ACTIVE_OR_DONE and job.remote_post_id:
            return {"job_id": job_id, "status": job.status, "idempotent_skip": True}
        if job.dead_lettered:
            return {"job_id": job_id, "status": job.status, "dead_lettered": True}

        # --- GLOBAL_PUBLISH_PAUSE kill switch (Phase 10): no remote publish on
        # ANY platform while paused. The job stays runnable — it is not failed.
        from app.ops.runtime_flags import emergency_stop_active, publish_paused

        if publish_paused() or emergency_stop_active():
            job.status = PublishStatus.READY.value
            _event(session, job.id, "PUBLISH_PAUSED",
                   {"reason": "GLOBAL_PUBLISH_PAUSE" if publish_paused() else "EMERGENCY_STOP"})
            return {"job_id": job_id, "status": job.status, "publish_paused": True,
                    "reason": "GLOBAL_PUBLISH_PAUSE" if publish_paused() else "EMERGENCY_STOP"}

        cap = get_capability(job.platform)
        account = session.get(PlatformAccount, job.platform_account_id) if job.platform_account_id else None
        acct_dict = {
            "connection_status": account.connection_status if account else "DISCONNECTED",
            "account_type": account.account_type if account else None,
        }
        publisher = get_publisher(job.platform, acct_dict)

        # --- capability short-circuit: MANUAL_ONLY / NOT_SUPPORTED / APP_REVIEW ---
        # These paths need neither a live token nor media preflight — emit the
        # honest status + package and stop.
        if not cap.auto_publish_possible:
            req = _build_request(session, job)
            result = publisher.publish(req)
            job.status = result.status.value
            _event(session, job.id, result.status.value, result.detail)
            _audit(session, job, "capability_stop",
                   {"publishing_status": cap.publishing_status, "needs": result.needs})
            _upsert_publication(session, job, status=result.status.value,
                                metadata_snapshot=result.detail, provider_mode=result.provider_mode)
            return {"job_id": job_id, "status": job.status, "needs": result.needs,
                    "detail": result.detail}

        # --- approval gate ---
        if job.run_mode in ("SEMI_AUTO", "FULL_AUTO", "AUTOPILOT") and job.approval_status != "APPROVED":
            job.status = PublishStatus.WAITING_APPROVAL.value
            _event(session, job.id, "WAITING_APPROVAL")
            return {"job_id": job_id, "status": job.status}

        job.started_at = job.started_at or _now()
        job.status = PublishStatus.QUEUED.value
        _event(session, job.id, "QUEUED")

        # --- crash recovery: adopt an existing remote post ---
        try:
            if reconcile_job(session, job, publisher):
                _event(session, job.id, "RECONCILED_REMOTE", {"remote_post_id": job.remote_post_id})
        except Exception:  # noqa: BLE001
            pass

        # --- token validity (skip for manual / not-supported) ---
        if cap.auto_publish_possible and account is not None:
            try:
                ensure_valid(session, account)
            except PublishError as e:
                return {"job_id": job_id, "status": _finalize_error(session, job, e)}

        # --- Platform Selection gate (Cross-Phase Intelligence Upgrade §AY/§AZ):
        # re-read the CURRENT selection right before the API call. A platform the
        # user turned off (or set to GENERATE_ONLY) — even after this job was
        # queued — must NOT reach the remote API.
        try:
            from app.intel.modes import is_learn_only
            from app.intel.platform_selection import publish_allowed

            camp_row = session.get(Campaign, job.campaign_id)
            if is_learn_only(getattr(camp_row, "execution_mode", None)):
                _sel_ok, _sel_mode = False, "LEARN_ONLY"
            else:
                _sel_ok, _sel_mode = publish_allowed(
                    session, campaign_id=job.campaign_id, platform=job.platform,
                    content_type=job.content_type or None)
        except Exception as _pe:  # noqa: BLE001 — fail closed
            _sel_ok, _sel_mode = False, f"SELECTION_ERROR:{_pe}"
        if not _sel_ok:
            job.status = PublishStatus.BLOCKED.value
            job.platform_selection_mode = _sel_mode
            job.last_error_type = "PLATFORM_DESELECTED"
            job.last_error_message = f"platform selection = {_sel_mode}; publish suppressed"[:2000]
            _event(session, job.id, "PLATFORM_DESELECTED", {"mode": _sel_mode})
            _audit(session, job, "platform_deselected", {"mode": _sel_mode})
            _upsert_publication(session, job, status=job.status, error_code="PLATFORM_DESELECTED",
                                error_message=f"platform selection = {_sel_mode}")
            return {"job_id": job_id, "status": job.status, "platform_selection": _sel_mode}

        # --- Phase 7 governance gate (§86-§87, §147): a BLOCK/FIX_REQUIRED/
        # HUMAN_REVIEW content can NEVER reach PUBLISHED, even via a direct
        # service call. Enforced unless GOVERNANCE_ENFORCE=false.
        if getattr(s, "governance_enforce", True):
            try:
                from app.governance.engine import govern_pre_publish

                gov = govern_pre_publish(session, job=job)
            except Exception as _ge:  # noqa: BLE001 — governance error must FAIL SAFE
                gov = {"decision": "HUMAN_REVIEW", "publishable": False, "hard_block": False,
                       "reason_codes": [f"GOVERNANCE.ERROR:{_ge}"], "state": "HUMAN_REVIEW"}
            job.governance_decision = gov.get("decision")
            _event(session, job.id, "GOVERNANCE", {"decision": gov.get("decision"),
                                                   "reason_codes": gov.get("reason_codes")})
            if not gov.get("publishable"):
                job.status = (PublishStatus.WAITING_APPROVAL.value
                              if gov.get("decision") == "HUMAN_REVIEW" and not gov.get("hard_block")
                              else PublishStatus.BLOCKED.value)
                job.last_error_type = "GOVERNANCE"
                job.last_error_message = ("; ".join(gov.get("reason_codes", []))[:2000]
                                          or gov.get("decision", "BLOCKED"))
                _audit(session, job, "governance_block",
                       {"decision": gov.get("decision"), "reason_codes": gov.get("reason_codes"),
                        "hard_block": gov.get("hard_block")})
                _upsert_publication(session, job, status=job.status, error_code="GOVERNANCE",
                                    error_message="; ".join(gov.get("reason_codes", []))[:2000])
                return {"job_id": job_id, "status": job.status, "governance": gov}

        # --- preflight ---
        pf = run_preflight(session, job)
        _event(session, job.id, "PREFLIGHT", {"ok": pf.ok, "issues": pf.issues})
        if not pf.ok:
            job.status = PublishStatus.BLOCKED.value
            job.last_error_type = PublishErrorType.MEDIA_INVALID.value
            job.last_error_message = "; ".join(pf.issues)[:2000]
            _audit(session, job, "preflight_block", {"issues": pf.issues})
            _upsert_publication(session, job, status=job.status, error_code="PREFLIGHT",
                               error_message="; ".join(pf.issues)[:2000])
            return {"job_id": job_id, "status": job.status, "issues": pf.issues}

        req = _build_request(session, job)

        # --- capability short-circuits (NOT_SUPPORTED / MANUAL / APP_REVIEW) ---
        try:
            result = publisher.publish(req)
        except PublishError as e:
            # MEDIA_INVALID -> normalize once and retry
            if e.error_type == PublishErrorType.MEDIA_INVALID and not job.platform_settings.get("_normalized"):
                changed = False
                for aid in list(job.media_asset_ids or []):
                    a = session.get(Asset, aid)
                    if a is None:
                        continue
                    norm = normalize_asset(session, a, job.platform)
                    if norm:
                        job.media_asset_ids = [norm.id if x == aid else x for x in job.media_asset_ids]
                        changed = True
                job.platform_settings = {**(job.platform_settings or {}), "_normalized": True}
                _event(session, job.id, "MEDIA_NORMALIZED", {"changed": changed})
                if changed:
                    req = _build_request(session, job)
                    try:
                        result = publisher.publish(req)
                    except PublishError as e2:
                        return {"job_id": job_id, "status": _finalize_error(session, job, e2)}
                else:
                    return {"job_id": job_id, "status": _finalize_error(session, job, e)}
            else:
                return {"job_id": job_id, "status": _finalize_error(session, job, e)}

        return {"job_id": job_id, **_apply_result(session, job, publisher, req, result, dry_run=req.dry_run)}


def _apply_result(session, job: PublishJob, publisher, req: PublishRequest,
                  result: PublishResult, *, dry_run: bool) -> dict:
    job.remote_container_id = result.remote_container_id or job.remote_container_id
    job.remote_post_id = result.remote_post_id or job.remote_post_id
    job.remote_publish_id = result.remote_publish_id or job.remote_publish_id
    job.remote_url = result.remote_url or job.remote_url

    st = result.status
    if dry_run and st == PublishStatus.READY:
        job.status = PublishStatus.READY.value
        _event(session, job.id, "DRY_RUN", {"payload": result.detail.get("payload")})
        _audit(session, job, "dry_run")
        _upsert_publication(session, job, status="DRY_RUN",
                            metadata_snapshot=result.detail, provider_mode=result.provider_mode)
        return {"status": job.status, "dry_run": True}

    if st in (PublishStatus.NOT_SUPPORTED, PublishStatus.WAITING_USER_ACTION,
              PublishStatus.WAITING_PLATFORM_ACTION):
        job.status = st.value
        _event(session, job.id, st.value, result.detail)
        _audit(session, job, "publish_pending", {"needs": result.needs})
        _upsert_publication(session, job, status=st.value, metadata_snapshot=result.detail,
                            provider_mode=result.provider_mode)
        return {"status": job.status, "needs": result.needs, "detail": result.detail}

    # PROCESSING -> bounded polling
    if st == PublishStatus.PROCESSING:
        job.status = PublishStatus.PROCESSING.value
        _event(session, job.id, "PROCESSING", {"container": result.remote_container_id})
        pm = PollingManager()
        handle = {"remote_container_id": result.remote_container_id}
        done, last = pm.run(
            step=lambda: publisher.get_publish_status(req, handle),
            done=lambda r: r.status in (PublishStatus.VERIFYING, PublishStatus.PUBLISHED),
            sleep=lambda _s: None,   # tests: don't actually sleep
        )
        if not done:
            job.status = PublishStatus.RETRY.value
            job.next_retry_at = retry_mod.plan(PublishErrorType.PROCESSING_ERROR, attempt=job.attempt_count + 1,
                                               max_attempts=job.max_attempts)["next_retry_at"]
            _event(session, job.id, "PROCESSING_TIMEOUT")
            _upsert_publication(session, job, status=job.status)
            return {"status": job.status}
        result = last
        job.remote_post_id = result.remote_post_id or job.remote_post_id
        job.remote_url = result.remote_url or job.remote_url
        st = result.status

    # VERIFYING -> confirm remote state
    if st in (PublishStatus.VERIFYING, PublishStatus.PUBLISHED):
        job.status = PublishStatus.VERIFYING.value
        _event(session, job.id, "VERIFYING", {"remote_post_id": job.remote_post_id})
        ok, url, vdetail = verify_published(publisher, job.remote_post_id)
        if ok:
            job.status = PublishStatus.PUBLISHED.value
            job.remote_url = url or job.remote_url
            job.published_at = job.published_at or _now()
            job.verified_at = _now()
            _event(session, job.id, "PUBLISHED", {"url": job.remote_url, **vdetail})
            _audit(session, job, "published", {"remote_post_id": job.remote_post_id, "url": job.remote_url})
            _schedule_analytics(session, job)
            _upsert_publication(session, job, status="PUBLISHED", remote_post_id=job.remote_post_id,
                                remote_container_id=job.remote_container_id,
                                remote_url=job.remote_url, published_at=job.published_at,
                                verified_at=job.verified_at, provider_mode=result.provider_mode,
                                metadata_snapshot={"title": job.title, "caption": job.caption,
                                                   "hashtags": job.hashtags, "ai_generated": job.ai_generated},
                                upload_completed_at=_now())
            return {"status": job.status, "remote_post_id": job.remote_post_id,
                    "remote_url": job.remote_url, "provider_mode": result.provider_mode,
                    "thread_remote_ids": result.thread_remote_ids}
        job.status = PublishStatus.RETRY.value
        job.attempt_count += 1
        job.next_retry_at = retry_mod.plan(PublishErrorType.PROCESSING_ERROR, attempt=job.attempt_count,
                                           max_attempts=job.max_attempts)["next_retry_at"]
        _event(session, job.id, "VERIFY_FAILED", vdetail)
        _upsert_publication(session, job, status=job.status, error_code="VERIFY_FAILED")
        return {"status": job.status, "detail": vdetail}

    job.status = st.value
    _upsert_publication(session, job, status=st.value, provider_mode=result.provider_mode)
    return {"status": job.status}
