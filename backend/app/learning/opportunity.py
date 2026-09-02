from __future__ import annotations

import statistics
from collections import defaultdict

from app.db.models import ContentFeature, LearningMemory, PerformanceScore, RevenueEntry

# Historical inputs Phase 4 (AUTOPILOT) will combine with a live Trend Score.
# This phase computes ONLY the historical side.


def opportunity_inputs(session, *, platform: str | None = None) -> list[dict]:
    feats = {f.content_id: f for f in session.query(ContentFeature).all()}
    scores = defaultdict(list)      # (cluster, platform) -> [score]
    for ps in session.query(PerformanceScore).all():
        if platform and ps.platform != platform:
            continue
        cf = feats.get(ps.content_id)
        if cf is None or not cf.topic_cluster:
            continue
        scores[(cf.topic_cluster, ps.platform)].append((ps.score, cf))

    fatigue_clusters = {
        m.topic_cluster for m in session.query(LearningMemory)
        .filter_by(memory_type="TOPIC", dimension="fatigue")
        if m.status not in ("DEPRECATED",)
    }
    rev_by_cluster = defaultdict(float)
    for re_ in session.query(RevenueEntry).all():
        cf = feats.get(re_.content_id) if re_.content_id else None
        if cf and cf.topic_cluster:
            rev_by_cluster[cf.topic_cluster] += re_.amount

    out = []
    for (cluster, plat), items in scores.items():
        vals = [s for s, _cf in items]
        n = len(vals)
        out.append({
            "topic_cluster": cluster,
            "platform": plat,
            "historical_performance": round(statistics.median(vals), 2),
            "performance_trend": round(vals[-1] - vals[0], 2) if n >= 2 else 0.0,
            "audience_fit": round(min(1.0, statistics.median(vals) / 100.0 + 0.1), 3),
            "revenue_performance": round(rev_by_cluster.get(cluster, 0.0), 2),
            "profit_performance": None,      # needs FX-resolved cost per cluster (deferred)
            "fatigue": cluster in fatigue_clusters,
            "sample_size": n,
            "confidence": round(min(0.9, 0.3 + 0.05 * n), 3),
        })
    out.sort(key=lambda x: (not x["fatigue"], x["historical_performance"]), reverse=True)
    return out
