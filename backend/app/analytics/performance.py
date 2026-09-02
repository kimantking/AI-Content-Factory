from __future__ import annotations

import statistics

from app.db.models import AnalyticsSnapshot, PerformanceScore, Publication

# Objective -> {normalized_metric: weight}. Missing metrics are renormalized out.
_OBJECTIVE_WEIGHTS: dict[str, dict[str, float]] = {
    "SHORT_VIDEO": {
        "VIEWS": {"views": 0.5, "shares": 0.2, "likes": 0.15, "comments": 0.15},
        "RETENTION": {"avg_view_percentage": 0.5, "watch_time_seconds": 0.25, "views": 0.15, "shares": 0.1},
        "WATCH_TIME": {"watch_time_seconds": 0.55, "avg_view_percentage": 0.25, "views": 0.2},
        "ENGAGEMENT": {"shares": 0.3, "comments": 0.25, "saves": 0.2, "likes": 0.15, "views": 0.1},
        "FOLLOWERS": {"followers_gained": 0.5, "subscribers_gained": 0.2, "shares": 0.2, "views": 0.1},
        "REVENUE": {"estimated_revenue": 0.7, "views": 0.2, "watch_time_seconds": 0.1},
        "PROFIT": {"estimated_revenue": 0.6, "views": 0.2, "shares": 0.2},
        "BRAND": {"saves": 0.35, "comments": 0.3, "shares": 0.2, "avg_view_percentage": 0.15},
        "BALANCED": {"views": 0.3, "avg_view_percentage": 0.2, "shares": 0.2, "comments": 0.15, "followers_gained": 0.15},
    },
    "LONG_VIDEO": {
        "VIEWS": {"views": 0.45, "watch_time_seconds": 0.3, "shares": 0.15, "likes": 0.1},
        "WATCH_TIME": {"watch_time_seconds": 0.5, "avg_view_percentage": 0.3, "views": 0.2},
        "RETENTION": {"avg_view_percentage": 0.55, "watch_time_seconds": 0.3, "views": 0.15},
        "ENGAGEMENT": {"comments": 0.3, "likes": 0.25, "shares": 0.25, "views": 0.2},
        "FOLLOWERS": {"subscribers_gained": 0.6, "watch_time_seconds": 0.2, "views": 0.2},
        "REVENUE": {"estimated_revenue": 0.65, "watch_time_seconds": 0.2, "views": 0.15},
        "PROFIT": {"estimated_revenue": 0.6, "watch_time_seconds": 0.25, "views": 0.15},
        "BRAND": {"comments": 0.35, "avg_view_percentage": 0.3, "shares": 0.2, "subscribers_gained": 0.15},
        "BALANCED": {"watch_time_seconds": 0.3, "avg_view_percentage": 0.2, "views": 0.2, "comments": 0.15, "subscribers_gained": 0.15},
    },
}
_DEFAULT_FAMILY = "SHORT_VIDEO"


def objective_weights(objective: str, content_type: str) -> dict[str, float]:
    fam = "LONG_VIDEO" if content_type.upper() in ("LONG_VIDEO", "BLOG_ARTICLE") else _DEFAULT_FAMILY
    table = _OBJECTIVE_WEIGHTS.get(fam, _OBJECTIVE_WEIGHTS[_DEFAULT_FAMILY])
    return dict(table.get(objective.upper(), table["BALANCED"]))


def _latest_snapshot(session, publication_id: str) -> AnalyticsSnapshot | None:
    return (session.query(AnalyticsSnapshot)
            .filter(AnalyticsSnapshot.publication_id == publication_id,
                    AnalyticsSnapshot.collection_status.in_(["SUCCESS", "PARTIAL"]))
            .order_by(AnalyticsSnapshot.collected_at.desc()).first())


def _metric_series(session, platform: str, content_type_family_long: bool, metric: str) -> list[float]:
    q = (session.query(getattr(AnalyticsSnapshot, metric))
         .join(Publication, Publication.id == AnalyticsSnapshot.publication_id)
         .filter(AnalyticsSnapshot.platform == platform,
                 getattr(AnalyticsSnapshot, metric).isnot(None)))
    return [float(v[0]) for v in q.all() if v[0] is not None]


def baseline(session, platform: str, content_type: str, metric: str) -> dict:
    vals = _metric_series(session, platform, content_type.upper() in ("LONG_VIDEO",), metric)
    if not vals:
        return {"n": 0}
    vals_sorted = sorted(vals)
    med = statistics.median(vals_sorted)
    p25 = statistics.quantiles(vals_sorted, n=4)[0] if len(vals_sorted) >= 2 else med
    p75 = statistics.quantiles(vals_sorted, n=4)[2] if len(vals_sorted) >= 2 else med
    return {"n": len(vals), "median": med, "p25": p25, "p75": p75,
            "mean": statistics.fmean(vals_sorted)}


def is_outlier(value: float, bl: dict) -> bool:
    if not bl or bl.get("n", 0) < 4:
        return False
    iqr = bl["p75"] - bl["p25"]
    return value > bl["p75"] + 1.5 * iqr or value < bl["p25"] - 1.5 * iqr


def relative_performance(value: float | None, bl: dict) -> float | None:
    if value is None or not bl or not bl.get("median"):
        return None
    return round(value / bl["median"], 3)


def compute_performance_score(session, publication_id: str, objective: str,
                              config_version: str = "v1") -> PerformanceScore:
    pub = session.get(Publication, publication_id)
    snap = _latest_snapshot(session, publication_id)
    from app.db.models import PlatformContent

    content = session.get(PlatformContent, pub.content_id) if pub and pub.content_id else None
    content_type = content.content_type if content else "SHORT_VIDEO"

    weights = objective_weights(objective, content_type)
    components: dict[str, dict] = {}
    outlier = False
    if snap is None:
        score = 0.0
    else:
        present = {}
        for metric, w in weights.items():
            v = getattr(snap, metric, None)
            if v is None:
                continue
            bl = baseline(session, pub.platform, content_type, metric)
            med = bl.get("median") or (v or 1.0)
            norm = min(1.0, float(v) / (2.0 * med)) if med else 0.0
            present[metric] = (w, norm)
            components[metric] = {"value": v, "weight": w, "norm": round(norm, 3),
                                  "baseline_median": round(med, 3), "n": bl.get("n", 0)}
            if is_outlier(float(v), bl):
                outlier = True
        total_w = sum(w for w, _ in present.values()) or 1.0
        score = round(100.0 * sum(w * n for w, n in present.values()) / total_w, 2)

    has_anomaly = bool(snap and snap.anomaly_flags)
    # relative score vs the platform's score distribution
    peer_scores = [p.score for p in session.query(PerformanceScore)
                   .filter(PerformanceScore.platform == pub.platform).all()]
    rel = None
    if peer_scores:
        peer_med = statistics.median(peer_scores) or 1.0
        rel = round(score / peer_med, 3) if peer_med else None

    existing = session.query(PerformanceScore).filter_by(
        publication_id=publication_id, objective=objective.upper(),
        objective_config_version=config_version).first()
    row = existing or PerformanceScore(publication_id=publication_id)
    row.content_id = pub.content_id
    row.campaign_id = pub.campaign_id
    row.platform = pub.platform
    row.content_type = content_type
    row.objective = objective.upper()
    row.objective_config_version = config_version
    row.score = score
    row.components = components
    row.relative_score = rel
    row.baseline_ref = {"metrics": list(weights)}
    row.is_outlier = outlier
    row.has_anomaly = has_anomaly
    row.snapshot_id = snap.id if snap else None
    if existing is None:
        session.add(row)
    session.flush()
    return row
