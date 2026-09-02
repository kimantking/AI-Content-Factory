from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.models import PublishJob
from app.publishing.base import PublishStatus

# DB-backed scheduler: all state lives in publish_jobs, so a backend / worker /
# beat restart loses nothing. Times are stored in UTC; the job keeps its display
# timezone.


def to_utc(local_dt: datetime, tz_name: str) -> datetime:
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=ZoneInfo(tz_name))
    return local_dt.astimezone(timezone.utc)


def schedule_job(session, job: PublishJob, when_local: datetime, tz_name: str) -> PublishJob:
    job.timezone = tz_name
    job.scheduled_at = to_utc(when_local, tz_name)
    job.status = PublishStatus.SCHEDULED.value
    session.flush()
    return job


def reschedule(session, job: PublishJob, when_local: datetime, tz_name: str | None = None) -> PublishJob:
    return schedule_job(session, job, when_local, tz_name or job.timezone)


def due_jobs(session, now: datetime | None = None, limit: int = 50) -> list[PublishJob]:
    now = now or datetime.now(timezone.utc)
    stmt = (
        select(PublishJob)
        .where(
            PublishJob.status.in_([PublishStatus.SCHEDULED.value, PublishStatus.RETRY.value]),
            PublishJob.dead_lettered.is_(False),
            PublishJob.scheduled_at.isnot(None),
            PublishJob.scheduled_at <= now,
        )
        .order_by(PublishJob.scheduled_at)
        .limit(limit)
    )
    rows = list(session.execute(stmt).scalars())
    # RETRY jobs also honour next_retry_at
    return [j for j in rows if not (j.next_retry_at and j.next_retry_at.replace(
        tzinfo=timezone.utc) > now)]
