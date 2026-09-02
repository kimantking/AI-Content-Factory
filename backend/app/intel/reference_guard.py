"""Originality check of generated output against the campaign's learned references
(spec §BN / §BW). Reuses the Phase 7 similarity metric. Deterministic; no LLM.

If a campaign has no learned references this is a no-op (returns ALLOW), so it has
zero effect on pre-upgrade content.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models_learn import ReferenceChunk, ReferenceSource
from app.governance.originality import text_similarity


def check_against_references(db: Session, *, campaign_id: str, workspace_id: str | None,
                            items: dict[str, str]) -> dict:
    """items: {kind: generated_text} e.g. {"HOOK": "...", "SCRIPT": "...", "TITLE": "..."}.
    Returns {decision, max_similarity, matches:[{kind, reference_id, score}]}."""
    s = get_settings()
    thr = s.reference_similarity_fix_threshold
    refs = (db.query(ReferenceSource)
            .filter(ReferenceSource.campaign_id == campaign_id,
                    ReferenceSource.status.in_(["EXTRACTED", "READY", "LOW_VALUE"]))
            .all())
    if not refs:
        return {"decision": "ALLOW", "max_similarity": 0.0, "matches": [], "n_references": 0}

    ref_texts: list[tuple[str, str]] = []
    for r in refs:
        chunks = db.query(ReferenceChunk).filter_by(reference_id=r.id).limit(12).all()
        blob = "\n".join(c.text for c in chunks) or (r.title or "")
        if blob.strip():
            ref_texts.append((r.id, blob))

    matches: list[dict] = []
    worst = 0.0
    for kind, gen in (items or {}).items():
        if not gen or len(gen.strip()) < 20:
            continue
        for rid, rtext in ref_texts:
            sim = text_similarity(gen[:6000], rtext[:6000])["combined"]
            if sim >= thr:
                matches.append({"kind": kind, "reference_id": rid, "score": round(sim, 4)})
            worst = max(worst, sim)

    decision = "FIX_REQUIRED" if matches else ("HUMAN_REVIEW" if worst >= thr - 0.1 else "ALLOW")
    return {"decision": decision, "max_similarity": round(worst, 4),
            "matches": matches[:20], "n_references": len(refs),
            "threshold": thr}
