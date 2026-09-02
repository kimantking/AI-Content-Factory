from __future__ import annotations

from app.db.models import PerformanceScore, TopicCandidate, TrendSource
from app.learning.memory import upsert_memory


def calibrate(session) -> dict:
    """Predicted Opportunity Score vs actual relative performance, per produced
    candidate. Feeds Phase 3 learning + adjusts trend-source value."""
    produced = (session.query(TopicCandidate)
                .filter(TopicCandidate.campaign_id.isnot(None),
                        TopicCandidate.opportunity_score.isnot(None)).all())
    if not produced:
        return {"calibrated": 0}

    over = under = ok = 0
    source_hits: dict[str, list[float]] = {}
    for cand in produced:
        scores = (session.query(PerformanceScore)
                  .filter_by(campaign_id=cand.campaign_id).all())
        if not scores:
            continue
        actual_rel = max((p.relative_score or 0) for p in scores) * 100.0  # ~0..>100
        predicted = cand.opportunity_score
        delta = actual_rel - predicted
        if delta < -25:
            over += 1
        elif delta > 25:
            under += 1
        else:
            ok += 1
        for sid in (cand.source_ids or []):
            source_hits.setdefault(sid, []).append(actual_rel)

    total = over + under + ok
    if total:
        upsert_memory(
            session, memory_type="SCORE_CALIBRATION", dimension="opportunity_vs_actual",
            statement=(f"Opportunity Score 예측 정확도: 적정 {ok}/{total}, "
                       f"과대예측 {over}, 과소예측 {under} (표본 {total})"),
            recommendation={"ok": ok, "over": over, "under": under, "n": total},
            confidence=min(0.85, 0.3 + 0.05 * total), sample_size=total,
            evidence_ids=[c.id for c in produced][:20], consistent=True,
        )

    # nudge trend-source value_score toward observed outcomes
    for sid, vals in source_hits.items():
        row = session.query(TrendSource).filter_by(source_id=sid).first()
        if row and vals:
            observed = sum(1 for v in vals if v >= 60) / len(vals)
            row.value_score = round(0.7 * row.value_score + 0.3 * observed, 3)
    session.flush()

    return {"calibrated": total, "over_prediction": over, "under_prediction": under,
            "well_calibrated": ok}
