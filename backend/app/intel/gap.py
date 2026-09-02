"""SkillGapDetector + Active-Learning recommendations.

Looks at our own Analytics (weak dimensions) and the shape of the reference
library (under-represented dataset types) and recommends what to learn next.
"""
from __future__ import annotations

from sqlalchemy import func as safunc
from sqlalchemy.orm import Session

from app.db.models import PerformanceScore
from app.db.models_learn import DatasetRecord

# weak analytics component -> dataset type to grow
_WEAK_TO_DATASET = {
    "retention": "VIDEO_DATASET",
    "hook_strength": "HOOK_DATASET",
    "watch_time": "EDITING_DATASET",
    "thumbnail_ctr": "THUMBNAIL_DATASET",
    "ctr": "THUMBNAIL_DATASET",
    "naturalness": "WRITING_DATASET",
    "voice_naturalness": "VOICE_DATASET",
    "audio_quality": "AUDIO_DATASET",
    "broll_relevance": "BROLL_DATASET",
    "shares": "HOOK_DATASET",
}

# a healthy library keeps at least this many active records per key type
_TARGET_COUNTS = {
    "VIDEO_DATASET": 30, "HOOK_DATASET": 20, "THUMBNAIL_DATASET": 20,
    "EDITING_DATASET": 20, "WRITING_DATASET": 20, "VOICE_DATASET": 12,
    "AUDIO_DATASET": 12, "BROLL_DATASET": 20, "SUBTITLE_DATASET": 12,
    "FACT_DATASET": 15, "KNOWLEDGE_DATASET": 15,
}


def library_counts(db: Session, *, workspace_id: str | None) -> dict[str, int]:
    q = db.query(DatasetRecord.dataset_type, safunc.count(DatasetRecord.id)).filter(
        DatasetRecord.active.is_(True))
    if workspace_id is not None:
        q = q.filter(DatasetRecord.workspace_id == workspace_id)
    return {t: n for t, n in q.group_by(DatasetRecord.dataset_type).all()}


def detect_gaps(db: Session, *, workspace_id: str | None, objective: str = "BALANCED") -> dict:
    counts = library_counts(db, workspace_id=workspace_id)

    # weak analytics dimensions (mean component score < 0.45 over recent scores)
    weak: dict[str, float] = {}
    scores = db.query(PerformanceScore).order_by(PerformanceScore.id.desc()).limit(200).all()
    agg: dict[str, list[float]] = {}
    for sc in scores:
        for k, v in (sc.components or {}).items():
            if isinstance(v, (int, float)):
                agg.setdefault(k, []).append(float(v))
    for k, vals in agg.items():
        m = sum(vals) / len(vals)
        norm = m / 100.0 if m > 1.5 else m
        if norm < 0.45:
            weak[k] = round(norm, 3)

    recs: list[dict] = []
    for k, v in sorted(weak.items(), key=lambda kv: kv[1]):
        dtype = _WEAK_TO_DATASET.get(k)
        if not dtype:
            continue
        have = counts.get(dtype, 0)
        recs.append({
            "reason": f"analytics '{k}' 약함 ({v:.2f})",
            "recommended_dataset": dtype, "have": have,
            "target": _TARGET_COUNTS.get(dtype, 15),
            "priority": "HIGH" if have < _TARGET_COUNTS.get(dtype, 15) / 2 else "MEDIUM",
        })

    for dtype, target in _TARGET_COUNTS.items():
        have = counts.get(dtype, 0)
        if have < target and not any(r["recommended_dataset"] == dtype for r in recs):
            recs.append({
                "reason": f"{dtype} 데이터가 부족합니다 ({have}/{target}).",
                "recommended_dataset": dtype, "have": have, "target": target,
                "priority": "LOW" if have >= target * 0.5 else "MEDIUM",
            })
    recs.sort(key=lambda r: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[r["priority"]])
    return {"library_counts": counts, "weak_dimensions": weak, "recommendations": recs[:12]}
