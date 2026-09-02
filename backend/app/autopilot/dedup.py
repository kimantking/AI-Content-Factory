from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.analytics.embedding import assign_cluster, cosine, embed
from app.db.models import Campaign, ContentFeature, PlatformContent, TopicCandidate

# recent-publish windows for the duplicate guard
_WINDOWS = (("7d", 7), ("30d", 30), ("90d", 90))


def _cluster_index(session) -> dict[str, list[float]]:
    idx: dict[str, list[float]] = {}
    for row in session.query(ContentFeature.topic_cluster, ContentFeature.topic_embedding):
        if row[0] and row[1] and row[0] not in idx:
            idx[row[0]] = row[1]
    for row in session.query(TopicCandidate.topic_cluster_id, TopicCandidate.topic):
        if row[0] and row[0] not in idx:
            idx[row[0]] = embed(row[1] or row[0])
    return idx


def assign_topic_cluster(session, topic: str) -> tuple[str, list[float]]:
    return assign_cluster(topic, _cluster_index(session), threshold=0.62)


def _published_topics(session, days: int, exclude_campaign_id: str | None = None
                      ) -> list[tuple[str, list[float]]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out: list[tuple[str, list[float]]] = []
    q = (session.query(Campaign.id, Campaign.topic)
         .join(PlatformContent, PlatformContent.campaign_id == Campaign.id)
         .filter(Campaign.created_at >= cutoff))
    seen = set()
    for cid, t in q:
        if exclude_campaign_id and cid == exclude_campaign_id:
            continue
        if t and t not in seen:
            seen.add(t)
            out.append((t, embed(t)))
    return out


def duplicate_status(session, topic: str, angle: str,
                     exclude_campaign_id: str | None = None) -> tuple[str, dict]:
    """NEW | SIMILAR | DUPLICATE | NEW_ANGLE against recent publishes.
    exclude_campaign_id skips the candidate's own just-created campaign."""
    vec = embed(topic)
    ang_vec = embed(f"{topic} {angle}")
    best = 0.0
    best_window = None
    for label, days in _WINDOWS:
        for pt, pv in _published_topics(session, days, exclude_campaign_id):
            sim = cosine(vec, pv)
            if sim > best:
                best, best_window = sim, label
    if best >= 0.8:
        # very close topic — is the angle materially different?
        ang_best = 0.0
        for _label, days in _WINDOWS[:1]:
            for pt, pv in _published_topics(session, days, exclude_campaign_id):
                ang_best = max(ang_best, cosine(ang_vec, pv))
        status = "NEW_ANGLE" if ang_best < 0.78 else "DUPLICATE"
    elif best >= 0.58:
        status = "SIMILAR"
    else:
        status = "NEW"
    return status, {"max_similarity": round(best, 3), "window": best_window}


def dedup_penalty(status: str) -> float:
    return {"NEW": 0.0, "NEW_ANGLE": -4.0, "SIMILAR": -12.0, "DUPLICATE": -35.0}.get(status, 0.0)
