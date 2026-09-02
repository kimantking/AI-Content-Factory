from __future__ import annotations

from datetime import datetime, timezone

from app.analytics.base import AnalyticsError
from app.analytics.feature_store import build_features, feature_hint
from app.analytics.metric_catalog import NORMALIZED_COLUMNS
from app.analytics.registry import get_analytics_provider
from app.db.models import (
    AnalyticsSnapshot,
    ContentFeature,
    PlatformContent,
    Publication,
    RevenueEntry,
)


def _prev_snapshot(session, publication_id: str, before: datetime) -> AnalyticsSnapshot | None:
    return (session.query(AnalyticsSnapshot)
            .filter(AnalyticsSnapshot.publication_id == publication_id,
                    AnalyticsSnapshot.collected_at < before)
            .order_by(AnalyticsSnapshot.collected_at.desc()).first())


def _detect_anomalies(prev: AnalyticsSnapshot | None, cur: dict) -> list[str]:
    flags: list[str] = []
    if prev is None:
        return flags
    for k in ("views", "impressions", "likes"):
        p, c = getattr(prev, k, None), cur.get(k)
        if p and c is not None and c < p * 0.5:
            flags.append(f"DATA_ANOMALY:{k}_dropped")
    return flags


def collect_snapshot(session, publication_id: str, window_label: str) -> AnalyticsSnapshot:
    """Collect one metric snapshot for one publication/window. Idempotent by
    (publication_id, window_label). A single metric failure => PARTIAL, never a
    lost snapshot; a provider-wide failure => a FAILED snapshot row (isolation)."""
    existing = (session.query(AnalyticsSnapshot)
                .filter_by(publication_id=publication_id, window_label=window_label).first())
    if existing:
        return existing

    pub = session.get(Publication, publication_id)
    if pub is None:
        raise ValueError("publication not found")

    now = datetime.now(timezone.utc)
    age_min = 0
    if pub.published_at:
        age_min = int((now - pub.published_at.replace(tzinfo=timezone.utc)).total_seconds() // 60)

    content_type = ""
    fh: dict = {}
    if pub.content_id:
        content = session.get(PlatformContent, pub.content_id)
        content_type = content.content_type if content else ""
        cf = session.query(ContentFeature).filter_by(content_id=pub.content_id).first()
        if cf is None:
            try:
                cf = build_features(session, pub.content_id)
            except ValueError:
                cf = None
        if cf is not None:
            fh = feature_hint(cf)

    snap = AnalyticsSnapshot(
        publication_id=publication_id, campaign_id=pub.campaign_id, content_id=pub.content_id,
        platform=pub.platform, platform_account_id=pub.platform_account_id,
        collected_at=now, content_age_minutes=age_min, window_label=window_label,
        currency="KRW",
    )

    if not pub.remote_post_id:
        snap.collection_status = "UNAVAILABLE"
        snap.data_source = "PLATFORM_API"
        session.add(snap)
        session.flush()
        return snap

    provider = get_analytics_provider(pub.platform)
    try:
        pm = provider.get_post_metrics(
            pub.remote_post_id, content_type=content_type,
            content_age_minutes=age_min, window_label=window_label, feature_hint=fh,
        )
    except AnalyticsError as e:
        snap.collection_status = "FAILED"
        snap.raw_payload = {"error_type": e.error_type.value, "message": str(e)}
        snap.provider = f"{pub.platform}-analytics"
        session.add(snap)
        session.flush()
        return snap

    for col in NORMALIZED_COLUMNS:
        mv = pm.metrics.get(col)
        if mv and mv.usable:
            setattr(snap, col, mv.value if col not in ("views", "impressions", "reach", "likes",
                    "comments", "shares", "saves", "reposts", "bookmarks", "quotes",
                    "followers_gained", "subscribers_gained", "profile_visits", "link_clicks")
                    else int(round(mv.value)))
    snap.raw_payload = pm.raw_payload
    snap.metric_availability = pm.availability_map()
    snap.data_source = pm.data_source
    snap.provider = pm.provider
    snap.collection_status = pm.collection_status
    snap.anomaly_flags = _detect_anomalies(_prev_snapshot(session, publication_id, now), {
        k: getattr(snap, k) for k in NORMALIZED_COLUMNS
    })
    session.add(snap)
    session.flush()

    rev = pm.metrics.get("estimated_revenue")
    if rev and rev.usable and rev.value:
        session.add(RevenueEntry(
            campaign_id=pub.campaign_id, content_id=pub.content_id, publication_id=pub.id,
            platform=pub.platform, source="PLATFORM_API", amount=float(rev.value),
            currency="KRW", is_estimate=True,
            provenance={"snapshot_id": snap.id, "provider": pm.provider, "window": window_label},
        ))
        session.flush()
    return snap
