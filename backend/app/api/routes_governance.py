from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.context import AuthContext
from app.auth.deps import current_user
from app.db.base import get_db
from app.db.models import Campaign
from app.db.models_gov import (
    ContentFingerprint,
    CopyrightClaim,
    GovernanceCase,
    RightsLedger,
    RightsManifest,
)
from app.governance import repair as _repair
from app.governance.engine import govern_campaign
from app.governance.manifest import build_manifest
from app.governance.policy import is_stale, seed_policy_registry

router = APIRouter(prefix="/api", tags=["governance"])


def _scope_campaign(db: Session, ctx: AuthContext, campaign_id: str) -> Campaign:
    camp = db.get(Campaign, campaign_id)
    if camp is None:
        raise HTTPException(404, "campaign not found")
    if camp.workspace_id is not None:
        ctx.assert_workspace(camp.workspace_id)
    return camp


# ---- governance ---------------------------------------------------- #

@router.post("/governance/check")
def governance_check(campaign_id: str = Body(..., embed=True),
                     content_id: str | None = Body(None, embed=True),
                     platform: str | None = Body(None, embed=True),
                     run_mode: str = Body("FULL_AUTO", embed=True),
                     stage: str = Body("pre_publish", embed=True),
                     db: Session = Depends(get_db), ctx: AuthContext = Depends(current_user)):
    _scope_campaign(db, ctx, campaign_id)
    return govern_campaign(db, campaign_id=campaign_id, content_id=content_id,
                           platform=platform, run_mode=run_mode, stage=stage)


@router.get("/governance/cases")
def list_cases(workspace_id: str | None = None, state: str | None = None,
               db: Session = Depends(get_db), ctx: AuthContext = Depends(current_user)):
    q = db.query(GovernanceCase)
    if not ctx.is_system_admin:
        allowed = list(ctx.memberships.keys()) or ["__none__"]
        q = q.filter(GovernanceCase.workspace_id.in_(allowed))
    if workspace_id:
        ctx.assert_workspace(workspace_id)
        q = q.filter(GovernanceCase.workspace_id == workspace_id)
    if state:
        q = q.filter(GovernanceCase.state == state)
    rows = q.order_by(GovernanceCase.created_at.desc()).limit(200).all()
    return [{"id": c.id, "campaign_id": c.campaign_id, "content_id": c.content_id,
             "case_type": c.case_type, "severity": c.severity, "state": c.state,
             "decision": c.decision, "reason_codes": c.reason_codes, "hard_block": c.hard_block,
             "detail": c.detail, "created_at": c.created_at.isoformat()} for c in rows]


@router.get("/governance/review")
def review_queue(workspace_id: str | None = None, db: Session = Depends(get_db),
                 ctx: AuthContext = Depends(current_user)):
    q = db.query(GovernanceCase).filter(GovernanceCase.state.in_(["HUMAN_REVIEW", "FIX_REQUIRED", "BLOCKED"]))
    if not ctx.is_system_admin:
        q = q.filter(GovernanceCase.workspace_id.in_(list(ctx.memberships.keys()) or ["__none__"]))
    if workspace_id:
        ctx.assert_workspace(workspace_id)
        q = q.filter(GovernanceCase.workspace_id == workspace_id)
    rows = q.order_by(GovernanceCase.severity.desc(), GovernanceCase.created_at.desc()).limit(200).all()
    return [{"id": c.id, "campaign_id": c.campaign_id, "case_type": c.case_type,
             "severity": c.severity, "state": c.state, "reason_codes": c.reason_codes,
             "hard_block": c.hard_block} for c in rows]


@router.post("/governance/cases/{case_id}/review")
def review_case(case_id: str, approve: bool = Body(..., embed=True),
                note: str = Body("", embed=True), db: Session = Depends(get_db),
                ctx: AuthContext = Depends(current_user)):
    c = db.get(GovernanceCase, case_id)
    if c is None:
        raise HTTPException(404, "case not found")
    if c.workspace_id is not None:
        ctx.assert_workspace(c.workspace_id)
        ctx.role = ctx.role_in(c.workspace_id)
        ctx.require("publish.approve")
    if c.hard_block:
        raise HTTPException(409, "hard governance block cannot be cleared by review — resolve the issue")
    from datetime import datetime, timezone
    c.state = "RESOLVED" if approve else "BLOCKED"
    c.resolved_at = datetime.now(timezone.utc)
    c.resolved_by = ctx.email or ctx.user_id
    c.resolution_note = note[:2000]
    from app.db.models_gov import GovernanceEvent
    db.add(GovernanceEvent(case_id=case_id, campaign_id=c.campaign_id, content_id=c.content_id,
                           kind="OVERRIDE", to_state=c.state, actor=ctx.email or ctx.user_id,
                           detail={"approve": approve, "note": note}))
    return {"id": c.id, "state": c.state}


@router.post("/governance/repair")
def governance_repair(campaign_id: str = Body(..., embed=True),
                      content_id: str | None = Body(None, embed=True),
                      reason_code: str = Body(..., embed=True),
                      db: Session = Depends(get_db), ctx: AuthContext = Depends(current_user)):
    camp = _scope_campaign(db, ctx, campaign_id)
    return _repair.apply_fix(db, campaign_id=campaign_id, content_id=content_id,
                             reason_code=reason_code, workspace_id=camp.workspace_id)


# ---- rights ------------------------------------------------------ #

@router.get("/rights")
def list_rights(campaign_id: str, db: Session = Depends(get_db),
                ctx: AuthContext = Depends(current_user)):
    _scope_campaign(db, ctx, campaign_id)
    rows = db.query(RightsLedger).filter_by(campaign_id=campaign_id).all()
    return [{"id": r.id, "asset_id": r.asset_id, "source_type": r.source_type,
             "license_type": r.license_type, "rights_status": r.rights_status,
             "commercial_use": r.commercial_use, "attribution_required": r.attribution_required,
             "expiration_at": r.expiration_at.isoformat() if r.expiration_at else None,
             "ai_generated": r.ai_generated, "watermark_detected": r.watermark_detected,
             "platform_restrictions": r.platform_restrictions} for r in rows]


@router.get("/rights/assets/{asset_id}")
def rights_for_asset(asset_id: str, db: Session = Depends(get_db),
                     ctx: AuthContext = Depends(current_user)):
    r = (db.query(RightsLedger).filter_by(asset_id=asset_id)
         .order_by(RightsLedger.created_at.desc()).first())
    if r is None:
        raise HTTPException(404, "no rights ledger for asset")
    if r.workspace_id is not None:
        ctx.assert_workspace(r.workspace_id)
    return {"id": r.id, **{k: getattr(r, k) for k in (
        "asset_id", "source_type", "source_provider", "license_type", "license_reference",
        "rights_status", "commercial_use", "derivative_use", "attribution_required",
        "attribution_text", "ai_generated", "model_provider", "model_name", "voice_kind",
        "consent_status", "person_status", "watermark_detected", "content_id_risk", "notes")},
        "expiration_at": r.expiration_at.isoformat() if r.expiration_at else None,
        "evidence_ids": r.evidence_ids}


@router.get("/rights/manifests")
def list_manifests(campaign_id: str, db: Session = Depends(get_db),
                   ctx: AuthContext = Depends(current_user)):
    _scope_campaign(db, ctx, campaign_id)
    rows = db.query(RightsManifest).filter_by(campaign_id=campaign_id).order_by(
        RightsManifest.created_at.desc()).all()
    return [{"id": m.id, "campaign_id": m.campaign_id, "content_id": m.content_id,
             "publication_id": m.publication_id, "governance_decision": m.governance_decision,
             "content_hash": m.content_hash, "is_published_snapshot": m.is_published_snapshot,
             "manifest": m.manifest, "created_at": m.created_at.isoformat()} for m in rows]


@router.post("/rights/manifests")
def make_manifest(campaign_id: str = Body(..., embed=True),
                  content_id: str | None = Body(None, embed=True),
                  publication_id: str | None = Body(None, embed=True),
                  published_snapshot: bool = Body(False, embed=True),
                  db: Session = Depends(get_db), ctx: AuthContext = Depends(current_user)):
    _scope_campaign(db, ctx, campaign_id)
    m = build_manifest(db, campaign_id=campaign_id, content_id=content_id,
                       publication_id=publication_id, published_snapshot=published_snapshot)
    return {"id": m.id, "manifest": m.manifest}


# ---- originality / policy / disclosure ------------------------- #

@router.post("/originality/check")
def originality_check(campaign_id: str = Body(..., embed=True),
                      db: Session = Depends(get_db), ctx: AuthContext = Depends(current_user)):
    _scope_campaign(db, ctx, campaign_id)
    res = govern_campaign(db, campaign_id=campaign_id, stage="post_render")
    return res.get("originality") or {"level": "ORIGINAL", "decision": "ALLOW",
                                      "note": "no render fingerprint yet"}


@router.get("/policy/status")
def policy_status(platform: str | None = None, db: Session = Depends(get_db),
                  ctx: AuthContext = Depends(current_user)):
    seed_policy_registry(db)
    from app.db.models_gov import PolicyRegistry
    plats = [platform] if platform else sorted({r[0] for r in db.query(PolicyRegistry.platform).distinct()})
    out = []
    for p in plats:
        rows = db.query(PolicyRegistry).filter_by(platform=p).all()
        out.append({"platform": p, "rules": len(rows), "stale": is_stale(db, p),
                    "unknown_rules": sum(1 for r in rows if r.status == "UNKNOWN"),
                    "version": rows[0].policy_version_or_reference if rows else None})
    return out


@router.get("/policy/verification")
def policy_verification(platform: str | None = None, db: Session = Depends(get_db),
                        ctx: AuthContext = Depends(current_user)):
    """AUDIT-P7-001 — the human-review work queue: platforms whose policy rules
    are stale or UNKNOWN. Does not fetch live policy pages."""
    from app.governance.policy_verify import verification_report

    return verification_report(db, platform=platform)


@router.post("/policy/verify")
def policy_verify(payload: dict = Body(...), db: Session = Depends(get_db),
                  ctx: AuthContext = Depends(current_user)):
    """A named reviewer attests they checked a platform's official policy."""
    from app.governance.policy_verify import record_verification

    try:
        res = record_verification(
            db, platform=payload["platform"],
            actor=payload.get("actor") or getattr(ctx, "email", "") or getattr(ctx, "user_id", ""),
            outcome=payload.get("outcome", "CONFIRMED_CURRENT"),
            note=payload.get("note", ""), rule_ids=payload.get("rule_ids"),
            source_reference=payload.get("source_reference"),
            activate_unknown=bool(payload.get("activate_unknown", False)),
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    db.commit()
    return res


@router.post("/disclosure/check")
def disclosure_check(campaign_id: str = Body(..., embed=True),
                     platform: str | None = Body(None, embed=True),
                     db: Session = Depends(get_db), ctx: AuthContext = Depends(current_user)):
    _scope_campaign(db, ctx, campaign_id)
    res = govern_campaign(db, campaign_id=campaign_id, platform=platform, stage="pre_publish")
    return res.get("disclosure") or {"decision": "NOT_REQUIRED"}


# ---- copyright claims ---------------------------------------- #

@router.get("/copyright/claims")
def list_claims(workspace_id: str | None = None, db: Session = Depends(get_db),
                ctx: AuthContext = Depends(current_user)):
    q = db.query(CopyrightClaim)
    if not ctx.is_system_admin:
        q = q.filter(CopyrightClaim.workspace_id.in_(list(ctx.memberships.keys()) or ["__none__"]))
    if workspace_id:
        ctx.assert_workspace(workspace_id)
        q = q.filter(CopyrightClaim.workspace_id == workspace_id)
    return [{"id": c.id, "platform": c.platform, "publication_id": c.publication_id,
             "claimant": c.claimant, "claim_type": c.claim_type, "status": c.status,
             "received_at": c.received_at.isoformat()} for c in q.order_by(
        CopyrightClaim.received_at.desc()).limit(200).all()]


@router.post("/copyright/claims")
def create_claim(payload: dict = Body(...), db: Session = Depends(get_db),
                 ctx: AuthContext = Depends(current_user)):
    from app.db.models import Publication

    pub = db.get(Publication, payload.get("publication_id")) if payload.get("publication_id") else None
    ws = payload.get("workspace_id")
    if ws:
        ctx.assert_workspace(ws)
    claim = CopyrightClaim(
        workspace_id=ws, platform=payload.get("platform", ""),
        publication_id=payload.get("publication_id"), asset_id=payload.get("asset_id"),
        claimant=payload.get("claimant", ""), claimed_segment=payload.get("claimed_segment", ""),
        claim_type=payload.get("claim_type", ""), evidence=payload.get("evidence", {}),
        status="RECEIVED",
    )
    db.add(claim)
    db.flush()
    # assemble a review (dispute) package from the rights ledger — never auto-filed
    if pub is not None:
        m = db.query(RightsManifest).filter_by(publication_id=pub.id).order_by(
            RightsManifest.created_at.desc()).first()
        if m:
            claim.dispute_package = {"manifest_id": m.id, "assets": m.manifest.get("assets", []),
                                     "attributions": m.manifest.get("attributions", []),
                                     "note": "review package only — not an automated legal filing"}
    return {"id": claim.id, "status": claim.status, "dispute_package": claim.dispute_package}
