from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

from app.trends.base import TrendError
from app.trends.capabilities import load_trend_capabilities
from app.trends.faults import trend_faults  # noqa: F401  (armable in tests)
from app.trends.registry import get_trend_provider

# Sources we actually scan by default: OWN_ANALYTICS (available) + anything that
# only needs auth (mock produces data; a real run needs the key). APPROVAL_REQUIRED
# / LIMITED / UNAVAILABLE sources are skipped and reported honestly.
_DEFAULT_SCAN_STATUSES = {"AVAILABLE", "AUTH_REQUIRED"}


def active_source_ids() -> list[str]:
    return [sid for sid, cap in load_trend_capabilities().items()
            if cap.auth_status in _DEFAULT_SCAN_STATUSES]


def skipped_source_ids() -> dict[str, str]:
    return {sid: cap.auth_status for sid, cap in load_trend_capabilities().items()
            if cap.auth_status not in _DEFAULT_SCAN_STATUSES}


def _norm(topic: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w가-힣 ]", "", topic.lower())).strip()


def _dedup_key(source_id: str, topic: str) -> str:
    return hashlib.sha256(f"{source_id}|{_norm(topic)}".encode()).hexdigest()[:32]


def ingest_trends(session, run_id: str, *, country: str = "KR", language: str = "ko",
                  per_source_limit: int = 15) -> dict:
    from app.db.models import RawTrendEvent, TrendSource

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    recent_keys = {
        r.dedup_key for r in session.query(RawTrendEvent.dedup_key)
        .filter(RawTrendEvent.detected_at >= cutoff).all()
    }

    per_source: dict[str, str] = {}
    written = 0
    for sid in active_source_ids():
        provider = get_trend_provider(sid)
        src_row = session.query(TrendSource).filter_by(source_id=sid).first()
        try:
            trends = provider.fetch_trending(country=country, language=language,
                                             limit=per_source_limit)
        except TrendError as e:
            per_source[sid] = f"ERROR:{e.error_type}"
            if src_row:
                src_row.last_failure = now
                src_row.health = "DOWN"
            continue
        except Exception as e:  # noqa: BLE001 — source isolation
            per_source[sid] = f"ERROR:{type(e).__name__}"
            if src_row:
                src_row.last_failure = now
                src_row.health = "DOWN"
            continue

        added = 0
        for t in trends:
            key = _dedup_key(sid, t.raw_topic)
            if key in recent_keys:
                continue
            recent_keys.add(key)
            session.add(RawTrendEvent(
                source_id=sid, run_id=run_id, raw_topic=t.raw_topic, title=t.title,
                description=t.description, published_at=t.published_at,
                country=t.country, language=t.language,
                engagement_signals={**t.engagement_signals, "interest_series": t.interest_series},
                source_metrics=t.source_metrics, url=t.url, reliability=t.reliability,
                dedup_key=key, raw_payload=t.raw_payload,
            ))
            added += 1
        written += added
        per_source[sid] = f"OK:{added}"
        if src_row:
            src_row.last_success = now
            src_row.health = "OK"
    session.flush()
    return {"written": written, "per_source": per_source, "skipped": skipped_source_ids()}
