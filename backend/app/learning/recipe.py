from __future__ import annotations

from collections import defaultdict

from app.db.models import ContentFeature, ContentRecipe, LearningMemory


def build_recipes(session, objective: str = "BALANCED") -> int:
    """Assemble a ContentRecipe per (platform, content_type, topic_cluster) from
    the MODERATE/STRONG memories that apply. Confidence = min of contributors."""
    mems = [m for m in session.query(LearningMemory)
            .filter(LearningMemory.status.in_(["MODERATE", "STRONG"])).all()
            if m.dimension and m.recommendation.get("lift", 0) is not None]

    feats = session.query(ContentFeature).all()
    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for f in feats:
        groups[(f.platform, f.content_type, f.topic_cluster or "_")].append(f.content_id)

    n = 0
    for (platform, ctype, cluster), content_ids in groups.items():
        if len(content_ids) < 4:
            continue
        applicable = [m for m in mems
                      if (m.platform in (None, platform)) and (m.content_type in (None, ctype))]
        pos = [m for m in applicable if m.recommendation.get("lift", 0) > 0]
        if not pos:
            continue
        recipe: dict = {"platform": platform, "content_type": ctype, "topic_cluster": cluster}
        for m in pos:
            rec = m.recommendation
            recipe[rec["dimension"]] = rec["value"]
        conf = round(min(m.confidence for m in pos), 3)
        n_samples = max(m.sample_size for m in pos)

        existing = session.query(ContentRecipe).filter_by(
            platform=platform, content_type=ctype, topic_cluster=cluster, objective=objective).first()
        row = existing or ContentRecipe(platform=platform, content_type=ctype,
                                        topic_cluster=cluster, objective=objective)
        row.recipe = recipe
        row.confidence = conf
        row.sample_size = n_samples
        row.evidence_ids = sorted({e for m in pos for e in (m.evidence_ids or [])})[:40]
        row.status = "STRONG" if conf >= 0.75 else "MODERATE" if conf >= 0.55 else "EXPERIMENTAL"
        if existing is None:
            session.add(row)
        n += 1
    session.flush()
    return n
