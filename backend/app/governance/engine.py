"""ContentGovernanceEngine (§1, §83-§87, §116) — orchestrates the sub-engines,
persists GovernanceCases + events, returns one GovernanceDecision.

Stages: pre-render / post-render / pre-publish. Deterministic. No LLM verdict.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Asset, Campaign, PlatformContent, Script, VerifiedFact
from app.db.models_gov import GovernanceCase, GovernanceEvent, RightsLedger
from app.governance import claims as _claims
from app.governance import disclosure as _disc
from app.governance import identity as _ident
from app.governance import originality as _orig
from app.governance import policy as _policy
from app.governance.decision import decide
from app.governance.rights import platform_allows


def _sub(engine: str, decision: str, *, codes=None, reqs=None, hard=False, sev="MEDIUM", detail=None):
    return {"engine": engine, "decision": decision, "reason_codes": codes or [],
            "requirements": reqs or [], "hard_block": hard, "severity": sev, "detail": detail or {}}


def _log_event(db: Session, *, campaign_id, content_id, kind, frm="", to="", actor="system", detail=None):
    db.add(GovernanceEvent(campaign_id=campaign_id, content_id=content_id, kind=kind,
                           from_state=frm, to_state=to, actor=actor, detail=detail or {}))
    db.flush()


def _open_case(db: Session, camp: Campaign, *, content_id, case_type, severity, decision,
               reason_codes, detail, hard_block):
    row = GovernanceCase(
        workspace_id=camp.workspace_id, brand_id=camp.brand_id, channel_id=camp.channel_id,
        campaign_id=camp.id, content_id=content_id, case_type=case_type, severity=severity,
        state={"BLOCK": "BLOCKED", "HUMAN_REVIEW": "HUMAN_REVIEW", "FIX_REQUIRED": "FIX_REQUIRED"}
              .get(decision, "PASS"),
        decision=decision, reason_codes=reason_codes, detail=detail,
        policy_version=_policy.POLICY_REGISTRY_VERSION, hard_block=hard_block,
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------- #

def _rights_stage(db: Session, camp: Campaign, content: PlatformContent | None,
                  platform: str, run_mode: str, ledgers: list[RightsLedger]) -> list[dict]:
    out: list[dict] = []
    now = datetime.now(timezone.utc)
    for led in ledgers:
        st = led.rights_status
        if st == "UNKNOWN_RIGHTS":
            hard = run_mode in ("FULL_AUTO", "AUTOPILOT", "SEMI_AUTO")
            out.append(_sub("rights", "BLOCK" if hard else "HUMAN_REVIEW",
                            codes=["RIGHTS.UNKNOWN_IN_AUTO" if hard else "RIGHTS.UNKNOWN"],
                            hard=hard, sev="HIGH",
                            detail={"asset_id": led.asset_id, "source_type": led.source_type}))
        elif st == "EXPIRED":
            out.append(_sub("rights", "BLOCK", codes=["RIGHTS.EXPIRED"], hard=True, sev="HIGH",
                            detail={"asset_id": led.asset_id, "expired_at": str(led.expiration_at)}))
        elif st == "BLOCKED":
            out.append(_sub("rights", "BLOCK", codes=["RIGHTS.BLOCKED"], hard=True, sev="CRITICAL",
                            detail={"asset_id": led.asset_id, "notes": led.notes}))
        elif st == "RESTRICTED":
            out.append(_sub("rights", "HUMAN_REVIEW", codes=["RIGHTS.RESTRICTED"], sev="MEDIUM",
                            detail={"asset_id": led.asset_id}))
        elif st in ("VERIFIED_WITH_ATTRIBUTION",):
            out.append(_sub("rights", "ALLOW_WITH_ATTRIBUTION", codes=["RIGHTS.ATTRIBUTION_NEEDED"],
                            reqs=[f"attribution:{led.asset_id}"], sev="LOW"))
        if led.watermark_detected:
            out.append(_sub("rights", "BLOCK", codes=["RIGHTS.WATERMARK"], hard=True, sev="HIGH",
                            detail={"asset_id": led.asset_id}))
        if led.expiration_at is not None:
            exp = led.expiration_at.replace(tzinfo=timezone.utc) if led.expiration_at.tzinfo is None else led.expiration_at
            sched = content and getattr(content, "payload", {}) or {}
            # scheduled-after-expiry check is done in pre_publish with the job's scheduled_at
        # platform music/asset restriction
        if not platform_allows(led, platform):
            out.append(_sub("rights", "BLOCK", codes=["RIGHTS.PLATFORM_RESTRICTED"], hard=True, sev="HIGH",
                            detail={"asset_id": led.asset_id, "platform": platform}))
        if led.content_id_risk and platform.startswith("youtube"):
            out.append(_sub("rights", "HUMAN_REVIEW", codes=["RIGHTS.CONTENT_ID_RISK"], sev="MEDIUM",
                            detail={"asset_id": led.asset_id}))
    if not ledgers:
        out.append(_sub("rights", "HUMAN_REVIEW", codes=["RIGHTS.NO_LEDGER"], sev="MEDIUM"))
    return out


def _identity_stage(script_body: str, ledgers: list[RightsLedger]) -> list[dict]:
    out: list[dict] = []
    wm = _ident.watermark_guard(ledgers)
    if wm["verdict"] == "BLOCK":
        out.append(_sub("watermark", "BLOCK", codes=["RIGHTS.WATERMARK"], hard=True, sev="HIGH",
                        detail=wm))
    for led in ledgers:
        vc = _ident.voice_clone_guard(led)
        if vc["verdict"] == "BLOCK":
            out.append(_sub("voice", "BLOCK", codes=["VOICE.CLONE_NO_CONSENT"], hard=True, sev="CRITICAL",
                            detail=vc))
        elif vc["verdict"] == "FIX_REQUIRED":
            out.append(_sub("voice", "FIX_REQUIRED", codes=["VOICE.TERMS_MISSING"], sev="MEDIUM", detail=vc))
        lk = _ident.likeness_risk(led)
        if lk["likeness_review_required"]:
            out.append(_sub("likeness", "HUMAN_REVIEW", codes=["LIKENESS.REVIEW"], sev="HIGH", detail=lk))
        tm = _ident.trademark_guard(led, script_text=script_body)
        if tm["verdict"] == "BLOCK":
            out.append(_sub("trademark", "BLOCK", codes=["TRADEMARK.BLOCK"], hard=True, sev="HIGH", detail=tm))
        elif tm["verdict"] == "HUMAN_REVIEW":
            out.append(_sub("trademark", "HUMAN_REVIEW", codes=["TRADEMARK.REVIEW"], sev="MEDIUM", detail=tm))
        if led.source_type == "SCREENSHOT":
            sg = _ident.screenshot_guard(led, ocr_text=led.notes or "")
            if sg["verdict"] == "BLOCK":
                out.append(_sub("privacy", "BLOCK", codes=["PRIVACY.HIGH_RISK_PII"], hard=True, sev="CRITICAL", detail=sg))
            elif sg["verdict"] in ("HUMAN_REVIEW", "FIX_REQUIRED"):
                out.append(_sub("privacy", sg["verdict"], codes=["PRIVACY.SCREENSHOT"], sev="MEDIUM", detail=sg))
    fe = _ident.fake_endorsement_guard(script_text=script_body, asset_ledgers=ledgers)
    if fe["verdict"] == "BLOCK":
        out.append(_sub("endorsement", "BLOCK", codes=["ENDORSEMENT.PUBLIC_FIGURE"], hard=True,
                        sev=fe.get("severity", "HIGH"), detail=fe))
    pii = _ident.scan_pii(script_body)
    if pii["verdict"] == "BLOCK":
        out.append(_sub("privacy", "BLOCK", codes=["PRIVACY.HIGH_RISK_PII"], hard=True, sev="CRITICAL", detail=pii))
    elif pii["verdict"] == "HUMAN_REVIEW":
        out.append(_sub("privacy", "HUMAN_REVIEW", codes=["PRIVACY.PII_IN_SCRIPT"], sev="MEDIUM", detail=pii))
    return out


def _policy_stage(db: Session, platform: str) -> list[dict]:
    out: list[dict] = []
    if _policy.is_stale(db, platform):
        out.append(_sub("policy", "HUMAN_REVIEW", codes=["POLICY.STALE"], sev="MEDIUM",
                        detail={"platform": platform, "max_age_days": get_settings().policy_max_age_days}))
    return out


def govern_campaign(db: Session, *, campaign_id: str, content_id: str | None = None,
                    platform: str | None = None, run_mode: str = "FULL_AUTO",
                    stage: str = "pre_publish", chart_values_by_claim: dict | None = None,
                    platform_variants: dict | None = None) -> dict:
    """Run governance for one campaign/content/platform. Persists cases + events
    and returns the decision dict."""
    camp = db.get(Campaign, campaign_id)
    if camp is None:
        raise ValueError(f"campaign {campaign_id} not found")

    # Legacy pre-Phase-7 content (no tenant scope, no rights ledger, governance
    # never run) passes through untouched — the gate only enforces on content
    # that has actually entered governance. New Phase-7 flows always create a
    # ledger, so BLOCKED content is still caught (§147, §120).
    _has_ledger = db.query(RightsLedger.id).filter_by(campaign_id=campaign_id).first() is not None
    if (not _has_ledger and camp.workspace_id is None
            and not getattr(camp, "governance_forced", False)):
        return {"campaign_id": campaign_id, "content_id": content_id, "platform": platform,
                "stage": stage, "decision": "ALLOW", "state": "PASS", "publishable": True,
                "hard_block": False, "reason_codes": ["GOVERNANCE.NOT_APPLICABLE_LEGACY"],
                "requirements": [], "score": 1.0, "sub_results": [], "disclosure": None,
                "claims": None, "originality": None, "provenance": {}}

    content = db.get(PlatformContent, content_id) if content_id else \
        db.query(PlatformContent).filter_by(campaign_id=campaign_id).first()
    platform = platform or (content.platform if content else "youtube_shorts")
    script = db.query(Script).filter_by(campaign_id=campaign_id).first()
    script_body = (script.body if script else "") or (content.script if content else "")

    _policy.seed_policy_registry(db)
    ledgers = db.query(RightsLedger).filter_by(campaign_id=campaign_id).all()
    assets = db.query(Asset).filter_by(campaign_id=campaign_id).all()
    visual_types = [a.meta.get("visual_type") or a.asset_type for a in assets if a.asset_type == "image"]
    scene_visual_types = []
    from app.db.models import Scene
    scenes = [{"estimated_duration": s.estimated_duration, "visual_type": s.visual_type,
               "camera_motion": s.camera_motion, "music_energy": s.music_energy}
              for s in db.query(Scene).filter_by(campaign_id=campaign_id).order_by(Scene.scene_order)]
    scene_visual_types = [s["visual_type"] for s in scenes]

    facts = [f.fact for f in db.query(VerifiedFact).filter_by(campaign_id=campaign_id).all()
             if f.status in ("VERIFIED", "PARTIALLY_VERIFIED")]

    sub: list[dict] = []
    sub += _rights_stage(db, camp, content, platform, run_mode, ledgers)
    sub += _identity_stage(script_body, ledgers)
    sub += _policy_stage(db, platform)

    # ---- disclosure ----
    prov = _disc.provenance_summary(db, [a.id for a in assets])
    disc = _disc.decide(db, platform=platform, provenance=prov)
    job_meta = (content.payload or {}).get("disclosure_meta", {}) if content else {}
    has_disclosure = bool(job_meta.get("disclosure_text")) or _disc.strip_disclosure_from_text_guard("AI가 생성", script_body) is False and any(
        m in script_body for m in _disc._DISCLOSURE_MARKERS)
    if disc["decision"] == "PLATFORM_FIELD_REQUIRED":
        if not job_meta.get("platform_ai_field"):
            sub.append(_sub("disclosure", "FIX_REQUIRED", codes=["DISCLOSURE.PLATFORM_FIELD_MISSING"],
                            reqs=["set platform AI/altered-content field"], sev="HIGH", detail=disc))
        else:
            sub.append(_sub("disclosure", "ALLOW_WITH_DISCLOSURE", codes=["DISCLOSURE.PLATFORM_FIELD_SET"], detail=disc))
    elif disc["decision"] == "REQUIRED":
        if not has_disclosure:
            sub.append(_sub("disclosure", "FIX_REQUIRED", codes=["DISCLOSURE.MISSING"],
                            reqs=["add AI disclosure to caption/description"], sev="HIGH", detail=disc))
        else:
            sub.append(_sub("disclosure", "ALLOW_WITH_DISCLOSURE", codes=["DISCLOSURE.PRESENT"], detail=disc))
    elif disc["decision"] == "RECOMMENDED":
        sub.append(_sub("disclosure", "ALLOW_WITH_DISCLOSURE" if has_disclosure else "ALLOW",
                        codes=["DISCLOSURE.RECOMMENDED"], reqs=([] if has_disclosure else ["disclosure recommended"]),
                        sev="LOW", detail=disc))
    elif disc["decision"] == "HUMAN_REVIEW":
        sub.append(_sub("disclosure", "HUMAN_REVIEW", codes=["DISCLOSURE.REVIEW"], sev="HIGH", detail=disc))

    # ---- claims ----
    cg = _claims.govern_claims(script_body=script_body, usable_fact_texts=facts,
                               chart_values_by_claim=chart_values_by_claim)
    if cg["decision"] == "BLOCK":
        sub.append(_sub("claims", "BLOCK", codes=["CLAIM.CHART_MISMATCH"], hard=True, sev="HIGH", detail=cg))
    elif cg["decision"] == "FIX_REQUIRED":
        sub.append(_sub("claims", "FIX_REQUIRED", codes=["CLAIM.UNSUPPORTED"], sev="MEDIUM", detail=cg))
    elif cg["decision"] == "HUMAN_REVIEW":
        sub.append(_sub("claims", "HUMAN_REVIEW", codes=["CLAIM.STALE"], sev="MEDIUM", detail=cg))

    # ---- originality (post-render / pre-publish only) ----
    orig_res = None
    if stage in ("post_render", "pre_publish") and scenes:
        render = next((a for a in assets if a.asset_type == "render"), None)
        thumb = next((a for a in assets if a.asset_type == "thumbnail"), None)
        thumb_ph = ""
        if thumb and thumb.storage_path:
            from app.governance.phash import phash as _ph
            thumb_ph = _ph(thumb.storage_path)
        ext_ratio = sum(1 for l in ledgers if l.source_type in ("SOCIAL_POST", "NEWS_MEDIA", "USER_UPLOAD")
                        and l.asset_id in {a.id for a in assets if a.asset_type == "image"}) / max(1, len(scene_visual_types))
        orig_res = _orig.check_originality(
            db, campaign_id=campaign_id, workspace_id=camp.workspace_id, brand_id=camp.brand_id,
            channel_id=camp.channel_id, script_body=script_body,
            hook=(content.hook if content else "") or "", title=(content.title if content else "") or camp.topic,
            scenes=scenes, visual_types=scene_visual_types, thumbnail_phash=thumb_ph,
            video_duration=(render.duration if render else None),
            external_footage_ratio=ext_ratio, platform_variants=platform_variants,
        )
        d = orig_res["decision"]
        if d == "BLOCK":
            sub.append(_sub("originality", "BLOCK", codes=[f"ORIGINALITY.{orig_res['level']}"],
                            hard=(orig_res["level"] == "DUPLICATE"), sev="HIGH", detail=orig_res))
        elif d in ("HUMAN_REVIEW", "FIX_REQUIRED"):
            sub.append(_sub("originality", d, codes=[f"ORIGINALITY.{orig_res['level']}"], sev="MEDIUM", detail=orig_res))

    # ---- similarity vs learned references (Cross-Phase Intelligence Upgrade §BN) ----
    try:
        from app.intel.reference_guard import check_against_references

        ref_chk = check_against_references(
            db, campaign_id=campaign_id, workspace_id=camp.workspace_id,
            items={"HOOK": (content.hook if content else "") or "",
                   "TITLE": (content.title if content else "") or "",
                   "SCRIPT": script_body})
        if ref_chk["decision"] == "FIX_REQUIRED":
            sub.append(_sub("reference_similarity", "FIX_REQUIRED",
                            codes=["ORIGINALITY.REFERENCE_TOO_SIMILAR"], sev="MEDIUM", detail=ref_chk))
        elif ref_chk["decision"] == "HUMAN_REVIEW":
            sub.append(_sub("reference_similarity", "HUMAN_REVIEW",
                            codes=["ORIGINALITY.REFERENCE_SIMILAR"], sev="LOW", detail=ref_chk))
    except Exception:  # noqa: BLE001 — reference guard must never break governance
        pass

    gd = decide(sub, run_mode=run_mode)

    # persist a case per non-ALLOW sub-result + a rollup event
    for r in sub:
        if r["decision"] != "ALLOW":
            _open_case(db, camp, content_id=content.id if content else None,
                       case_type=r["engine"].upper(), severity=r.get("severity", "MEDIUM"),
                       decision=r["decision"], reason_codes=r["reason_codes"], detail=r["detail"],
                       hard_block=r.get("hard_block", False))
    _log_event(db, campaign_id=campaign_id, content_id=content.id if content else None,
               kind="DECISION", to=gd.state,
               detail={"decision": gd.decision, "stage": stage, "reason_codes": gd.reason_codes,
                       "hard_block": gd.hard_block})
    if content is not None:
        content.governance_state = gd.state
        content.governance_decision = gd.decision
        content.payload = {**(content.payload or {}),
                           "disclosure_meta": {**job_meta,
                                               "disclosure_required": disc["decision"] in ("REQUIRED", "PLATFORM_FIELD_REQUIRED"),
                                               "disclosure_type": disc["disclosure_type"],
                                               "disclosure_text": job_meta.get("disclosure_text") or disc["text"],
                                               "ai_generated": prov["ai_generated"],
                                               "synthetic_video": prov["synthetic_video"],
                                               "synthetic_image": prov["synthetic_image"],
                                               "synthetic_voice": prov["synthetic_voice"],
                                               "materially_altered": prov["materially_altered"],
                                               "policy_version": _policy.POLICY_REGISTRY_VERSION}}
        db.flush()

    return {
        "campaign_id": campaign_id, "content_id": content.id if content else None,
        "platform": platform, "stage": stage,
        "decision": gd.decision, "state": gd.state, "publishable": gd.publishable,
        "hard_block": gd.hard_block, "reason_codes": gd.reason_codes,
        "requirements": gd.requirements, "score": gd.score,
        "sub_results": sub, "disclosure": disc, "claims": cg, "originality": orig_res,
        "provenance": prov,
    }


def govern_pre_publish(db: Session, *, job) -> dict:
    """Entry point for the Publisher preflight. Reads the job's platform + run
    mode. Also fails EXPIRED-at-scheduled-time."""
    content = db.get(PlatformContent, job.content_id) if getattr(job, "content_id", None) else None
    res = govern_campaign(db, campaign_id=job.campaign_id,
                          content_id=job.content_id if content else None,
                          platform=job.platform, run_mode=job.run_mode or "FULL_AUTO",
                          stage="pre_publish")
    # scheduled-after-expiry
    sched = getattr(job, "scheduled_at", None)
    if sched is not None:
        sched = sched.replace(tzinfo=timezone.utc) if sched.tzinfo is None else sched
        for led in db.query(RightsLedger).filter_by(campaign_id=job.campaign_id).all():
            if led.expiration_at is not None:
                exp = led.expiration_at.replace(tzinfo=timezone.utc) if led.expiration_at.tzinfo is None else led.expiration_at
                if exp < sched:
                    res["decision"] = "BLOCK"
                    res["state"] = "BLOCKED"
                    res["publishable"] = False
                    res["hard_block"] = True
                    res["reason_codes"] = sorted(set(res["reason_codes"] + ["RIGHTS.EXPIRED"]))
    job.governance_decision = res["decision"]
    return res
