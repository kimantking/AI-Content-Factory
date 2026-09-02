from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.models import AnalyticsJob, Publication

SHORT_WINDOWS = [("1h", 60), ("6h", 360), ("24h", 1440), ("72h", 4320),
                 ("7d", 10080), ("14d", 20160), ("30d", 43200)]
LONG_WINDOWS = [("1h", 60), ("24h", 1440), ("72h", 4320),
                ("7d", 10080), ("14d", 20160), ("30d", 43200)]


def windows_for(content_type: str) -> list[tuple[str, int]]:
    return LONG_WINDOWS if content_type.upper() in ("LONG_VIDEO", "BLOG_ARTICLE") else SHORT_WINDOWS


def create_jobs_for_publication(session, publication: Publication, content_type: str,
                                windows: list[tuple[str, int]] | None = None) -> list[AnalyticsJob]:
    base = publication.published_at or datetime.now(timezone.utc)
    windows = windows or windows_for(content_type)
    have = {j.window_label for j in
            session.query(AnalyticsJob).filter_by(publication_id=publication.id)}
    out: list[AnalyticsJob] = []
    for label, minutes in windows:
        if label in have:
            continue
        job = AnalyticsJob(
            publication_id=publication.id, campaign_id=publication.campaign_id,
            platform=publication.platform, window_label=label,
            scheduled_at=base + timedelta(minutes=minutes), status="SCHEDULED",
        )
        session.add(job)
        out.append(job)
    session.flush()
    return out


def due_analytics_jobs(session, now: datetime | None = None, limit: int = 100) -> list[AnalyticsJob]:
    now = now or datetime.now(timezone.utc)
    return list(
        session.query(AnalyticsJob)
        .filter(AnalyticsJob.status.in_(["SCHEDULED", "RETRY"]),
                AnalyticsJob.scheduled_at <= now)
        .order_by(AnalyticsJob.scheduled_at)
        .limit(limit)
    )
