from __future__ import annotations

from app.db.models import PublishJob
from app.publishing.base import ACTIVE_OR_DONE, PublishStatus
from app.publishing.publishers import BasePublisher


def reconcile_job(session, job: PublishJob, publisher: BasePublisher) -> bool:
    """Crash between remote success and DB save.

    If a job is mid-flight (or looks unpublished) but the platform already has a
    post for its idempotency key, adopt that remote id instead of re-publishing.
    A duplicate post is a critical failure, so this runs before every publish.
    """
    if job.remote_post_id:
        return False
    if not job.idempotency_key:
        return False
    try:
        existing = publisher.client.find_by_idempotency(job.idempotency_key)
    except Exception:  # noqa: BLE001 — reconciliation is best-effort
        return False
    if not existing:
        return False
    job.remote_post_id = existing["id"]
    job.remote_url = existing.get("url")
    if PublishStatus(job.status) not in ACTIVE_OR_DONE:
        job.status = PublishStatus.VERIFYING.value
    session.flush()
    return True
