from __future__ import annotations

from datetime import datetime, timezone

from app.analytics.embedding import cosine, embed
from app.config import get_settings
from app.db.models import ContentFeature, LearningMemory

MEMORY_TYPES = [
    "BRAND", "CHANNEL", "TOPIC", "AUDIENCE", "HOOK", "SCRIPT", "VISUAL", "VOICE",
    "SUBTITLE", "THUMBNAIL", "PLATFORM", "TIMING", "NATURALNESS", "REVENUE",
    "FAILURE", "COMPLIANCE",
]
MEMORY_STATUS = ["EXPERIMENTAL", "WEAK", "MODERATE", "STRONG", "DEPRECATED"]


def status_for(sample_size: int, confidence: float, consistent: bool = True) -> str:
    s = get_settings()
    if not consistent:
        return "WEAK"
    if sample_size >= s.memory_min_strong_sample and confidence >= 0.75:
        return "STRONG"
    if sample_size >= s.memory_min_moderate_sample and confidence >= 0.55:
        return "MODERATE"
    if sample_size >= 2 and confidence >= 0.4:
        return "WEAK"
    return "EXPERIMENTAL"


def _key(mem_type: str, platform: str | None, content_type: str | None,
         topic_cluster: str | None, dimension: str | None) -> tuple:
    return (mem_type, platform or "", content_type or "", topic_cluster or "", dimension or "")


def upsert_memory(session, *, memory_type: str, statement: str, platform: str | None = None,
                  content_type: str | None = None, topic_cluster: str | None = None,
                  dimension: str | None = None, recommendation: dict | None = None,
                  confidence: float = 0.0, sample_size: int = 0,
                  evidence_ids: list[str] | None = None, consistent: bool = True,
                  hard_policy: bool = False) -> LearningMemory:
    assert memory_type in MEMORY_TYPES, memory_type
    rows = session.query(LearningMemory).filter_by(memory_type=memory_type).all()
    match = next(
        (r for r in rows if _key(r.memory_type, r.platform, r.content_type, r.topic_cluster,
                                 r.dimension) == _key(memory_type, platform, content_type,
                                                      topic_cluster, dimension)),
        None,
    )
    status = status_for(sample_size, confidence, consistent)
    if match is None:
        match = LearningMemory(memory_type=memory_type, platform=platform,
                               content_type=content_type, topic_cluster=topic_cluster,
                               dimension=dimension, hard_policy=hard_policy)
        session.add(match)
    match.statement = statement
    match.recommendation = recommendation or {}
    match.confidence = round(confidence, 3)
    match.sample_size = sample_size
    match.evidence_ids = evidence_ids or []
    match.status = status
    match.last_validated_at = datetime.now(timezone.utc)
    match.meta = {**(match.meta or {}), "consistent": consistent}
    session.flush()
    return match


def deprecate_stale(session, *, older_than_days: int = 60) -> int:
    cutoff = datetime.now(timezone.utc)
    n = 0
    for m in session.query(LearningMemory).filter(LearningMemory.status != "DEPRECATED"):
        lv = (m.last_validated_at or m.created_at)
        lv = lv.replace(tzinfo=timezone.utc) if lv and lv.tzinfo is None else lv
        if lv and (cutoff - lv).days > older_than_days and not m.pinned:
            m.status = "DEPRECATED"
            n += 1
    session.flush()
    return n


_TOK_PER_MEM = 60   # rough


def retrieve_memories(session, *, platform: str | None = None, content_type: str | None = None,
                      topic: str | None = None, objective: str | None = None,
                      brand_id: str | None = None) -> list[LearningMemory]:
    """Rank by relevance (topic cosine) + confidence + recency, cap by
    MAX_MEMORY_ITEMS and MAX_MEMORY_TOKENS. Never dumps every memory."""
    s = get_settings()
    q = session.query(LearningMemory).filter(LearningMemory.status.notin_(["DEPRECATED", "EXPERIMENTAL"]))
    rows = q.all()
    topic_vec = embed(topic) if topic else None
    cluster_vecs: dict[str, list[float]] = {}
    if topic_vec is not None:
        for cluster, emb in session.query(
            ContentFeature.topic_cluster, ContentFeature.topic_embedding
        ):
            if cluster and emb and cluster not in cluster_vecs:
                cluster_vecs[cluster] = emb

    # keyword pass (Mem0-style multi-signal fusion): salient topic tokens the
    # retrieval can match against a memory's statement/dimension even when the
    # topic-cluster embedding link is weak.
    import re as _re

    topic_tokens = {t for t in _re.findall(r"[\w가-힣]{2,}", (topic or "").lower())} \
        if topic else set()

    now = datetime.now(timezone.utc)
    scored: list[tuple[float, LearningMemory]] = []
    for m in rows:
        rel = 1.0
        if platform and m.platform and m.platform != platform:
            rel *= 0.3
        if content_type and m.content_type and m.content_type != content_type:
            rel *= 0.6
        if topic_vec is not None and m.topic_cluster and m.topic_cluster in cluster_vecs:
            rel *= 0.4 + 0.6 * max(0.0, cosine(topic_vec, cluster_vecs[m.topic_cluster]))
        if objective and m.recommendation.get("objective") and m.recommendation["objective"] != objective:
            rel *= 0.7
        lv = (m.last_validated_at or m.created_at)
        lv = lv.replace(tzinfo=timezone.utc) if lv and lv.tzinfo is None else lv
        age_days = (now - lv).days if lv else 999
        recency = max(0.2, 1.0 - age_days / 90.0)
        rank = rel * (0.4 + 0.6 * m.confidence) * recency
        # keyword-overlap boost — additive, bounded, never overrides confidence gating
        if topic_tokens:
            mtext = f"{m.statement or ''} {m.dimension or ''}".lower()
            hits = sum(1 for t in topic_tokens if t in mtext)
            if hits:
                rank *= 1.0 + min(0.5, 0.12 * hits)
        if m.pinned:
            rank += 1.0
        scored.append((rank, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[LearningMemory] = []
    tokens = 0
    for _rank, m in scored:
        if len(out) >= s.max_memory_items:
            break
        tokens += _TOK_PER_MEM
        if tokens > s.max_memory_tokens:
            break
        out.append(m)
    return out
