"""Governance Decision Engine + State Machine (§77-§82, §116).

Combines sub-engine verdicts into one decision with reason codes. A `BLOCK`
(or any `hard_block` case) can NOT be lifted by an agent or a plain UI approval
(§79-§80). Invalid state transitions are rejected (§116).
"""
from __future__ import annotations

from dataclasses import dataclass, field

GOV_STATES = ("PENDING", "SCANNING", "PASS", "PASS_WITH_REQUIREMENTS",
              "FIX_REQUIRED", "HUMAN_REVIEW", "BLOCKED", "RESOLVED")

_TRANSITIONS = {
    "PENDING": {"SCANNING", "BLOCKED"},
    "SCANNING": {"PASS", "PASS_WITH_REQUIREMENTS", "FIX_REQUIRED", "HUMAN_REVIEW", "BLOCKED"},
    "FIX_REQUIRED": {"SCANNING", "BLOCKED", "RESOLVED"},
    "HUMAN_REVIEW": {"PASS", "PASS_WITH_REQUIREMENTS", "FIX_REQUIRED", "BLOCKED", "RESOLVED"},
    "PASS_WITH_REQUIREMENTS": {"PASS", "RESOLVED", "SCANNING", "BLOCKED"},
    "PASS": {"RESOLVED", "SCANNING", "BLOCKED"},          # re-scan or a claim can re-block
    "BLOCKED": {"SCANNING", "RESOLVED"},                   # only via a real fix / authorised review
    "RESOLVED": set(),
}

# decision severity order (higher wins)
_ORDER = {"ALLOW": 0, "ALLOW_WITH_ATTRIBUTION": 1, "ALLOW_WITH_DISCLOSURE": 1,
          "FIX_REQUIRED": 2, "HUMAN_REVIEW": 3, "BLOCK": 4}
_DECISION_STATE = {
    "ALLOW": "PASS", "ALLOW_WITH_DISCLOSURE": "PASS_WITH_REQUIREMENTS",
    "ALLOW_WITH_ATTRIBUTION": "PASS_WITH_REQUIREMENTS", "FIX_REQUIRED": "FIX_REQUIRED",
    "HUMAN_REVIEW": "HUMAN_REVIEW", "BLOCK": "BLOCKED",
}


def valid_transition(frm: str, to: str) -> bool:
    return to in _TRANSITIONS.get(frm, set())


@dataclass
class GovernanceDecision:
    decision: str = "ALLOW"
    state: str = "PASS"
    reason_codes: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)   # disclosures / attributions to apply
    hard_block: bool = False
    cases: list[dict] = field(default_factory=list)         # per-sub-engine findings
    score: float = 1.0

    @property
    def publishable(self) -> bool:
        return self.decision in ("ALLOW", "ALLOW_WITH_DISCLOSURE", "ALLOW_WITH_ATTRIBUTION")


# reason codes that are ALWAYS a hard block (cannot be UI-overridden — §80)
_HARD_BLOCK_CODES = {
    "RIGHTS.UNKNOWN_IN_AUTO", "RIGHTS.EXPIRED", "RIGHTS.WATERMARK", "RIGHTS.BLOCKED",
    "VOICE.CLONE_NO_CONSENT", "POLICY.COPYRIGHT_BLOCK", "PRIVACY.HIGH_RISK_PII",
    "CLAIM.CHART_MISMATCH", "ENDORSEMENT.PUBLIC_FIGURE",
}


def decide(sub_results: list[dict], *, run_mode: str = "FULL_AUTO") -> GovernanceDecision:
    """sub_results: [{engine, decision, reason_codes:[...], requirements:[...],
                      hard_block:bool, severity, detail}]"""
    worst = "ALLOW"
    codes: list[str] = []
    reqs: list[str] = []
    hard = False
    weights = []
    for r in sub_results:
        d = r.get("decision", "ALLOW")
        if _ORDER.get(d, 0) > _ORDER.get(worst, 0):
            worst = d
        for c in r.get("reason_codes", []):
            codes.append(c)
            if c in _HARD_BLOCK_CODES:
                hard = True
        reqs.extend(r.get("requirements", []))
        if r.get("hard_block"):
            hard = True
        weights.append(1.0 - _ORDER.get(d, 0) / 4.0)

    # a FIX_REQUIRED/HUMAN_REVIEW does not become ALLOW just because avg is high
    if hard:
        worst = "BLOCK"
    score = round(sum(weights) / len(weights), 3) if weights else 1.0
    return GovernanceDecision(
        decision=worst, state=_DECISION_STATE[worst], reason_codes=sorted(set(codes)),
        requirements=sorted(set(reqs)), hard_block=hard, cases=sub_results, score=score,
    )


def apply_human_override(current: GovernanceDecision, *, reviewer: str, approve: bool,
                         note: str = "") -> tuple[GovernanceDecision, str | None]:
    """An authorised reviewer may clear HUMAN_REVIEW / FIX_REQUIRED (soft) items.
    Hard blocks are NOT clearable this way (§80). Returns (new_decision, error)."""
    if current.hard_block:
        return current, "hard governance block cannot be cleared by review — resolve the underlying issue"
    if not approve:
        return GovernanceDecision(decision="BLOCK", state="BLOCKED",
                                  reason_codes=current.reason_codes + ["REVIEW.REJECTED"],
                                  hard_block=current.hard_block, cases=current.cases), None
    return GovernanceDecision(
        decision="ALLOW_WITH_DISCLOSURE" if current.requirements else "ALLOW",
        state="PASS_WITH_REQUIREMENTS" if current.requirements else "PASS",
        reason_codes=current.reason_codes + [f"REVIEW.APPROVED_BY:{reviewer}"],
        requirements=current.requirements, hard_block=False, cases=current.cases,
    ), None
