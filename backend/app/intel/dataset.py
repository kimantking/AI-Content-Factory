"""Reference Dataset Engine + DataCurator.

A reference is not stored as a plain Memory. Each analysis output becomes a
`DatasetRecord` with quality / trust / relevance / freshness / originality scores
and a `learning_weight`. The curator lowers weight or deactivates duplicate /
spam / low-quality / wrong-language / stale / rights-problem records.
"""
from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy.orm import Session

from app.db.models_learn import DatasetRecord, ReferenceSource
from app.intel.router import DATASET_FOR_ANALYSIS

_WORD = re.compile(r"[\w가-힣]+")


def _payload_hash(dataset_type: str, payload: dict) -> str:
    blob = dataset_type + "|" + json.dumps(payload, sort_keys=True, ensure_ascii=False)[:8000]
    return hashlib.sha256(blob.encode()).hexdigest()


def write_records(db: Session, *, reference: ReferenceSource, analyses: dict,
                  topic_cluster: str = "", language: str = "") -> list[DatasetRecord]:
    """analyses: {analysis_kind: {"data": {...}, "confidence": float}}."""
    out: list[DatasetRecord] = []
    existing_hashes = {
        r.content_hash for r in db.query(DatasetRecord.content_hash)
        .filter(DatasetRecord.workspace_id == reference.workspace_id).all()
    }
    for kind, blob in analyses.items():
        dtype = DATASET_FOR_ANALYSIS.get(kind)
        if not dtype:
            continue
        data = blob.get("data") or {}
        if not data or data == {"status": "EMPTY"}:
            continue
        h = _payload_hash(dtype, data)
        if h in existing_hashes:
            continue
        existing_hashes.add(h)
        rec = DatasetRecord(
            workspace_id=reference.workspace_id, brand_id=reference.brand_id,
            channel_id=reference.channel_id, reference_id=reference.id,
            dataset_type=dtype, content_hash=h, payload=data,
            quality_score=reference.quality_score, trust_score=reference.trust_score,
            relevance_score=reference.relevance_score, freshness_score=reference.freshness_score,
            originality_score=reference.originality_score,
            learning_weight=reference.learning_weight * float(blob.get("confidence", 1.0) or 1.0),
            rights_status=reference.rights_status,
            language=language or reference.language, topic_cluster=topic_cluster or reference.topic_cluster,
            tags=list(reference.tags or []),
        )
        db.add(rec)
        out.append(rec)
    db.flush()
    return out


# --------------------------------------------------------------------- #
#  DataCurator
# --------------------------------------------------------------------- #

_SPAM = re.compile(r"(buy now|click here|limited offer|무료 체험|지금 구매|카톡 문의|텔레그램)", re.I)


def curate(db: Session, *, workspace_id: str | None, expected_language: str = "") -> dict:
    """Sweep dataset records: flag + down-weight duplicate / spam / low quality /
    wrong language / stale / rights problem / bad metadata."""
    q = db.query(DatasetRecord)
    if workspace_id is not None:
        q = q.filter(DatasetRecord.workspace_id == workspace_id)
    rows = q.all()
    seen_hash: dict[str, str] = {}
    stats = {"duplicate": 0, "spam": 0, "low_quality": 0, "wrong_language": 0,
             "stale": 0, "rights_problem": 0, "bad_metadata": 0, "deactivated": 0}
    for r in rows:
        flags: list[str] = []
        if r.content_hash in seen_hash and seen_hash[r.content_hash] != r.id:
            flags.append("duplicate")
        else:
            seen_hash[r.content_hash] = r.id
        blob = json.dumps(r.payload or {}, ensure_ascii=False)
        if _SPAM.search(blob):
            flags.append("spam")
        if r.quality_score and r.quality_score < 0.3:
            flags.append("low_quality")
        if expected_language and r.language and r.language[:2].lower() != expected_language[:2].lower():
            flags.append("wrong_language")
        if r.freshness_score and r.freshness_score < 0.2:
            flags.append("stale")
        if r.rights_status in ("UNKNOWN_RIGHTS", "BLOCKED", "EXPIRED", "DISPUTED"):
            flags.append("rights_problem")
        if not (r.payload or {}):
            flags.append("bad_metadata")

        if flags != list(r.curator_flags or []):
            r.curator_flags = flags
        for f in flags:
            stats[f] = stats.get(f, 0) + 1
        deactivate = bool({"duplicate", "spam", "rights_problem", "bad_metadata"} & set(flags))
        if deactivate and r.active:
            r.active = False
            stats["deactivated"] += 1
        if flags and r.active:
            r.learning_weight = round(max(0.05, r.learning_weight * (0.5 ** len(flags))), 3)
    db.flush()
    stats["scanned"] = len(rows)
    return stats


def active_records(db: Session, *, workspace_id: str | None, dataset_type: str | None = None,
                   topic_cluster: str | None = None, min_weight: float = 0.0) -> list[DatasetRecord]:
    q = db.query(DatasetRecord).filter(DatasetRecord.active.is_(True))
    if workspace_id is not None:
        q = q.filter(DatasetRecord.workspace_id == workspace_id)
    if dataset_type:
        q = q.filter(DatasetRecord.dataset_type == dataset_type)
    if topic_cluster:
        q = q.filter(DatasetRecord.topic_cluster == topic_cluster)
    if min_weight:
        q = q.filter(DatasetRecord.learning_weight >= min_weight)
    return q.order_by(DatasetRecord.learning_weight.desc()).all()
