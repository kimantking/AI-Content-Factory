from __future__ import annotations

from datetime import datetime, timezone

from app.autopilot.dedup import duplicate_status
from app.config import get_settings
from app.db.models import TopicCandidate

# result of a pre-publish recheck for a trend/current-event campaign
CONTINUE = "CONTINUE"
UPDATE_RESEARCH = "UPDATE_RESEARCH"
HOLD = "HOLD"
CANCEL = "CANCEL"


def pre_publish_recheck(session, candidate_id: str) -> dict:
    """Run right before a produced campaign is published. Sunk cost is NOT a
    reason to publish a dead trend."""
    s = get_settings()
    cand = session.get(TopicCandidate, candidate_id)
    if cand is None:
        return {"verdict": CANCEL, "reason": "candidate missing"}

    now = datetime.now(timezone.utc)
    reasons: list[str] = []
    verdict = CONTINUE

    # trend still alive?
    if cand.expires_at and cand.expires_at.replace(tzinfo=timezone.utc) < now:
        reasons.append("trend TTL expired")
        verdict = HOLD if cand.trend_type in ("SEASONAL", "RECURRING") else CANCEL

    # opportunity dropped since selection?
    orig = (cand.explanation or {}).get("score", {}).get("opportunity_score", cand.opportunity_score or 0)
    if cand.opportunity_score is not None and orig and cand.opportunity_score < orig * 0.6:
        reasons.append(f"opportunity dropped {orig}->{cand.opportunity_score}")
        verdict = CANCEL if verdict == CONTINUE else verdict

    # a near-duplicate appeared in the meantime? (ignore this candidate's own campaign)
    dup, meta = duplicate_status(session, cand.topic, cand.angle,
                                 exclude_campaign_id=cand.campaign_id)
    if dup == "DUPLICATE" and cand.dedup_status != "DUPLICATE":
        reasons.append("duplicate appeared after selection")
        verdict = HOLD if verdict == CONTINUE else verdict

    # risk changed upward?
    if cand.risk_level in ("HIGH", "CRITICAL"):
        reasons.append(f"risk={cand.risk_level}")
        if cand.risk_level == "CRITICAL":
            verdict = CANCEL

    if verdict == CANCEL:
        cand.status = "CANCELLED"
        cand.explanation = {**(cand.explanation or {}), "cancel_reason": reasons}
    session.flush()
    return {"verdict": verdict, "reason": "; ".join(reasons) or "ok", "dup": meta}
