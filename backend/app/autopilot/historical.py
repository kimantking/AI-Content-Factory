from __future__ import annotations

import statistics

from app.analytics.embedding import cosine, embed
from app.db.models import (
    ContentFeature,
    LearningMemory,
    PerformanceScore,
    RevenueEntry,
)


def _similar_scores(session, topic: str, *, min_sim: float = 0.55):
    """PerformanceScore rows whose content is topically similar. Outliers &
    anomalies excluded so one viral clip can't inflate the historical score."""
    vec = embed(topic)
    feats = {f.content_id: f for f in session.query(ContentFeature).all()}
    rows = []
    for ps in session.query(PerformanceScore).all():
        cf = feats.get(ps.content_id)
        if cf is None or not cf.topic_embedding:
            continue
        if cosine(vec, cf.topic_embedding) < min_sim:
            continue
        rows.append((ps, cf))
    clean = [(ps, cf) for ps, cf in rows if not (ps.is_outlier or ps.has_anomaly)]
    return clean or rows


def historical_score(session, topic: str) -> tuple[float, int, float]:
    rows = _similar_scores(session, topic)
    if not rows:
        return 50.0, 0, 0.2                       # neutral prior, low confidence
    scores = [ps.score for ps, _ in rows]
    med = statistics.median(scores)
    n = len(scores)
    conf = min(0.9, 0.25 + 0.05 * n)
    return round(med, 2), n, round(conf, 3)


def audience_fit_score(session, topic: str, platform: str | None = None) -> float:
    rows = _similar_scores(session, topic, min_sim=0.5)
    if not rows:
        return 55.0                               # allow exploration, don't block
    rel = [ps.relative_score for ps, _ in rows if ps.relative_score is not None]
    if not rel:
        return 55.0
    m = statistics.median(rel)
    return round(max(0.0, min(100.0, 50.0 + (m - 1.0) * 45.0)), 2)


def revenue_score(session, topic: str) -> tuple[float, bool]:
    rows = _similar_scores(session, topic, min_sim=0.5)
    cids = {cf.content_id for _ps, cf in rows}
    if not cids:
        return 45.0, True
    amounts = [re_.amount for re_ in session.query(RevenueEntry)
               if re_.content_id in cids]
    if not amounts:
        return 40.0, True
    est_flag = any(re_.is_estimate for re_ in session.query(RevenueEntry)
                   if re_.content_id in cids)
    avg = statistics.fmean(amounts)
    return round(max(0.0, min(100.0, avg / 5000.0)), 2), est_flag


def fatigue_score(session, topic_cluster: str | None) -> float:
    """High = fatigued (bad). Uses Phase 3 TOPIC fatigue memories."""
    if not topic_cluster:
        return 20.0
    m = (session.query(LearningMemory)
         .filter_by(memory_type="TOPIC", dimension="fatigue", topic_cluster=topic_cluster)
         .first())
    if m and m.status not in ("DEPRECATED",):
        return round(min(100.0, 55.0 + 40.0 * m.confidence), 2)
    return 20.0
