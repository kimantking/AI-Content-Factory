"""AUDIT-P7-001 — platform-policy verification (human-in-the-loop).

The policy registry rows are shape-fixtures. This module does NOT fetch live
policy pages (that stays NEEDS_PRODUCTION_ENVIRONMENT). It:

  * `verification_report()` — a deterministic sweep flagging every platform whose
    rules are stale (older than `policy_max_age_days`) or carry `UNKNOWN` status,
    i.e. the work queue for a human reviewer;
  * `record_verification()` — a reviewer attests "I checked platform X's official
    policy on <date>"; it bumps `last_verified_at`, optionally updates a rule's
    source reference, and — only when `activate_unknown=True` and the reviewer is
    named — flips an `UNKNOWN` rule to `ACTIVE`. Everything is written to
    `GovernanceEvent` so the attestation is auditable. `LEGAL_REVIEW_REQUIRED`
    labelling is preserved: nothing is auto-activated without an explicit,
    attributed review.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models_gov import GovernanceEvent, PolicyRegistry
from app.governance.policy import seed_policy_registry


def _age_days(ts: datetime | None) -> float | None:
    if ts is None:
        return None
    ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
    return round((datetime.now(timezone.utc) - ts).total_seconds() / 86400, 1)


def verification_report(db: Session, *, platform: str | None = None) -> dict:
    seed_policy_registry(db)
    max_age = getattr(get_settings(), "policy_max_age_days", 120)
    q = db.query(PolicyRegistry)
    if platform:
        q = q.filter(PolicyRegistry.platform == platform)
    rows = q.all()
    by_platform: dict[str, list[PolicyRegistry]] = {}
    for r in rows:
        by_platform.setdefault(r.platform, []).append(r)

    items = []
    for plat, prs in sorted(by_platform.items()):
        newest = max((p.last_verified_at for p in prs if p.last_verified_at), default=None)
        age = _age_days(newest)
        unknown = [p.rule_id for p in prs if p.status == "UNKNOWN"]
        stale = age is None or age > max_age
        items.append({
            "platform": plat, "rules": len(prs),
            "newest_verified_at": newest.isoformat() if newest else None,
            "age_days": age, "max_age_days": max_age,
            "stale": stale, "unknown_rules": unknown,
            "needs_review": bool(stale or unknown),
            "review_label": "LEGAL_REVIEW_REQUIRED" if (stale or unknown) else "OK",
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platforms_total": len(items),
        "platforms_needing_review": sum(1 for i in items if i["needs_review"]),
        "queue": [i for i in items if i["needs_review"]],
        "all": items,
    }


def record_verification(db: Session, *, platform: str, actor: str, outcome: str = "CONFIRMED_CURRENT",
                        note: str = "", rule_ids: list[str] | None = None,
                        source_reference: str | None = None,
                        activate_unknown: bool = False) -> dict:
    """A human attests they verified `platform`'s official policy. Returns a summary."""
    actor = (actor or "").strip()
    if not actor:
        raise ValueError("verification requires a named reviewer (actor)")
    if outcome not in ("CONFIRMED_CURRENT", "UPDATED", "STILL_UNKNOWN"):
        raise ValueError(f"unknown outcome: {outcome}")

    q = db.query(PolicyRegistry).filter(PolicyRegistry.platform == platform)
    if rule_ids:
        q = q.filter(PolicyRegistry.rule_id.in_(rule_ids))
    rows = q.all()
    if not rows:
        raise ValueError(f"no policy rules for platform {platform}")

    now = datetime.now(timezone.utc)
    activated: list[str] = []
    for r in rows:
        r.last_verified_at = now
        if source_reference:
            r.source_reference = source_reference
        if r.status == "UNKNOWN" and activate_unknown and outcome != "STILL_UNKNOWN":
            r.status = "ACTIVE"
            activated.append(r.rule_id)
    db.add(GovernanceEvent(
        kind="POLICY_VERIFIED",
        actor=actor,
        detail={"platform": platform, "outcome": outcome, "note": note,
                "rules_touched": [r.rule_id for r in rows], "activated": activated,
                "source_reference": source_reference},
    ))
    db.flush()
    return {"platform": platform, "actor": actor, "outcome": outcome,
            "rules_touched": len(rows), "activated_rules": activated,
            "verified_at": now.isoformat()}


def due_for_review(db: Session) -> list[str]:
    """Platforms a periodic task should raise to a human. No side effects."""
    return [i["platform"] for i in verification_report(db)["queue"]]
