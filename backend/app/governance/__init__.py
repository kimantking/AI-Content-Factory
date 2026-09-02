"""Phase 7 — Content Governance Layer.

Rights · License · Provenance · Copyright-risk · Originality · Similarity ·
AI-disclosure · Platform-policy · Claim-governance · Likeness · Trademark ·
Commercial-disclosure · Governance-decision.

Deterministic where possible: metadata / hashes / DB / rules / embeddings /
registries. LLM is not used for a governance verdict. A `BLOCK` cannot be
overridden by an agent (§79); some human-review items are overridable by an
authorised user, hard blocks are not (§80).
"""
from __future__ import annotations

from app.governance.decision import (
    GOV_STATES,
    GovernanceDecision,
    decide,
    valid_transition,
)
from app.governance.engine import govern_campaign, govern_pre_publish

__all__ = [
    "GovernanceDecision",
    "decide",
    "valid_transition",
    "GOV_STATES",
    "govern_campaign",
    "govern_pre_publish",
]
