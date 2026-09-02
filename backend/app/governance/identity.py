"""Likeness / voice-clone / trademark / watermark / privacy guards (§35-§45).

Deterministic checks over ledger metadata + text. Advanced CV (logo/face/PII
detection) is an OPTIONAL adapter (`app.governance.adapters`); its absence never
fakes a pass — the fields stay UNKNOWN and route to review where risk is implied.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.db.models_gov import RightsLedger

_PII = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "phone_kr": re.compile(r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b"),
    "card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "rrn_kr": re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b"),   # Korean resident reg. no
}
_ENDORSE_VERBS = ("추천합니다", "추천했", "협찬받", "이 제품을 씁니다", "사용 중입니다",
                  "endorses", "recommends", "partnered with us")
_PUBLIC_FIGURE_HINT = ("대통령", "장관", "의원", "회장", "CEO", "감독", "배우", "가수", "선수")


def likeness_risk(led: RightsLedger) -> dict:
    """REAL_PERSON | FICTIONAL_PERSON | SYNTHETIC_PERSON | UNKNOWN_PERSON +
    LIKENESS_REVIEW_REQUIRED flag."""
    ps = led.person_status or "UNKNOWN_PERSON"
    review = False
    reasons = []
    if ps == "REAL_PERSON" and led.ai_generated:
        review = True
        reasons.append("AI-altered depiction of a real person")
    if ps == "SYNTHETIC_PERSON":
        # synthetic person is fine unless it resembles a real/public figure
        if led.trademark_flag == "MISLEADING_ASSOCIATION_RISK":
            review = True
            reasons.append("synthetic person resembling a real/public figure")
    if ps == "UNKNOWN_PERSON" and led.source_type in ("USER_UPLOAD", "SOCIAL_POST", "SCREENSHOT"):
        review = True
        reasons.append("unidentified person in user/social asset")
    return {"person_status": ps, "likeness_review_required": review, "reasons": reasons}


def voice_clone_guard(led: RightsLedger) -> dict:
    """CLONED_VOICE requires documented consent + provider terms (§37). Unknown ⇒ BLOCK."""
    vk = led.voice_kind or "UNKNOWN"
    if vk != "CLONED_VOICE":
        return {"voice_kind": vk, "verdict": "OK"}
    if led.consent_status in ("USER_CONFIRMED", "DOCUMENTED"):
        if not led.model_terms_reference:
            return {"voice_kind": vk, "verdict": "FIX_REQUIRED",
                    "reason": "cloned voice consent present but provider/model terms not referenced"}
        return {"voice_kind": vk, "verdict": "OK"}
    return {"voice_kind": vk, "verdict": "BLOCK",
            "reason": f"cloned voice consent_status={led.consent_status or 'UNKNOWN'} — consent not established"}


def trademark_guard(led: RightsLedger, *, script_text: str = "") -> dict:
    """EDITORIAL_CONTEXT | PRODUCT_REFERENCE | SPONSOR_AUTHORIZED | USER_OWNED |
    UNKNOWN_USAGE | MISLEADING_ASSOCIATION_RISK."""
    flag = led.trademark_flag or "UNKNOWN_USAGE"
    reasons = []
    verdict = "OK"
    if flag == "MISLEADING_ASSOCIATION_RISK":
        verdict = "HUMAN_REVIEW"
        reasons.append("possible misleading brand association")
    if flag == "UNKNOWN_USAGE" and led.watermark_detected:
        verdict = "BLOCK"
        reasons.append("third-party logo/watermark with unknown usage rights")
    return {"trademark_flag": flag, "verdict": verdict, "reasons": reasons}


def fake_endorsement_guard(*, script_text: str, asset_ledgers: list[RightsLedger]) -> dict:
    """§41 — a real/synthetic public figure + a product recommendation in the same
    piece is HIGH/CRITICAL."""
    low = (script_text or "")
    endorse = any(v in low for v in _ENDORSE_VERBS)
    figure_asset = any((l.person_status in ("REAL_PERSON", "SYNTHETIC_PERSON")) for l in asset_ledgers)
    figure_text = any(h in low for h in _PUBLIC_FIGURE_HINT)
    if (figure_asset or figure_text) and endorse:
        sev = "CRITICAL" if any(l.person_status == "SYNTHETIC_PERSON" for l in asset_ledgers) else "HIGH"
        return {"verdict": "BLOCK", "severity": sev,
                "reason": "public-figure likeness combined with a product endorsement"}
    return {"verdict": "OK"}


def watermark_guard(asset_ledgers: list[RightsLedger]) -> dict:
    hits = [l.asset_id for l in asset_ledgers if l.watermark_detected]
    return {"verdict": "BLOCK" if hits else "OK", "assets": hits}


def scan_pii(text: str) -> dict:
    found = {k: bool(rx.search(text or "")) for k, rx in _PII.items()}
    high = found["card"] or found["rrn_kr"]
    return {"found": {k: v for k, v in found.items() if v},
            "verdict": "BLOCK" if high else ("HUMAN_REVIEW" if any(found.values()) else "OK")}


def screenshot_guard(led: RightsLedger, *, ocr_text: str = "") -> dict:
    """§44-§45 — don't auto-capture/publish logged-in private / DM / dashboard screens."""
    reasons = []
    verdict = "OK"
    priv_markers = ("받은편지함", "DM", "쪽지", "대시보드", "결제 내역", "계좌", "주문 내역",
                    "inbox", "dashboard", "billing", "settings")
    if any(m in (ocr_text or "") for m in priv_markers):
        verdict = "HUMAN_REVIEW"
        reasons.append("screenshot may show a private/logged-in view")
    pii = scan_pii(ocr_text)
    if pii["verdict"] == "BLOCK":
        verdict = "BLOCK"
        reasons.append("screenshot contains high-risk personal data")
    elif pii["verdict"] == "HUMAN_REVIEW" and verdict == "OK":
        verdict = "HUMAN_REVIEW"
        reasons.append("screenshot contains personal identifiers")
    if led.source_type == "SCREENSHOT" and not led.source_url_or_id:
        reasons.append("screenshot source URL/section not recorded")
        if verdict == "OK":
            verdict = "FIX_REQUIRED"
    return {"verdict": verdict, "reasons": reasons, "pii": pii["found"]}
