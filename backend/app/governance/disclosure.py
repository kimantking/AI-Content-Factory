"""AI Disclosure Engine (§31-§34) — provenance → per-platform disclosure decision.

Not for hiding AI use — for meeting each platform's transparency rule. Disclosure
info attached here must never be stripped downstream (§34): `assert_not_stripped`.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models_gov import RightsLedger
from app.governance import policy as _policy

_SYNTH_KO = "이 콘텐츠에는 AI가 생성/합성한 요소가 포함되어 있습니다."
_ALTERED_KO = "이 콘텐츠는 실제 장면을 상당 부분 변형·합성하여 제작되었습니다."


def provenance_summary(db: Session, asset_ids: list[str]) -> dict:
    rows = (db.query(RightsLedger)
            .filter(RightsLedger.asset_id.in_(asset_ids or ["__none__"])).all())
    synth_image = any(r.ai_generated and r.source_type in ("AI_GENERATED", "GENERATED_IMAGE") for r in rows)
    synth_video = any(r.ai_generated and r.source_type == "GENERATED_VIDEO" for r in rows)
    synth_voice = any(r.voice_kind in ("CLONED_VOICE",) or
                      (r.ai_generated and r.source_type == "GENERATED_AUDIO") for r in rows)
    tts_voice = any(r.voice_kind == "GENERIC_TTS" for r in rows)
    synth_person = any(r.person_status == "SYNTHETIC_PERSON" for r in rows)
    real_person_synth = any(r.person_status == "REAL_PERSON" and r.ai_generated for r in rows)
    any_ai = synth_image or synth_video or synth_voice or tts_voice or any(r.ai_generated for r in rows)
    # "materially altered": AI edits applied to real footage
    materially_altered = any(r.ai_generated and r.source_type in ("STOCK_LICENSED", "USER_UPLOAD") for r in rows)
    return {
        "ai_generated": any_ai,
        "ai_assisted": any_ai and not (synth_video or synth_image),
        "synthetic_image": synth_image,
        "synthetic_video": synth_video,
        "synthetic_voice": synth_voice,
        "tts_voice": tts_voice,
        "synthetic_person": synth_person,
        "real_person_synthetic": real_person_synth,
        "materially_altered": materially_altered,
    }


def decide(db: Session, *, platform: str, provenance: dict) -> dict:
    """NOT_REQUIRED | RECOMMENDED | REQUIRED | PLATFORM_FIELD_REQUIRED | HUMAN_REVIEW."""
    rules = [r for r in _policy.rules_for(db, platform, policy_type="SYNTHETIC_MEDIA")]
    stale = _policy.is_stale(db, platform)

    has_synthetic = provenance.get("synthetic_video") or provenance.get("synthetic_image") \
        or provenance.get("synthetic_voice") or provenance.get("synthetic_person") \
        or provenance.get("materially_altered")
    any_ai = provenance.get("ai_generated")

    decision = "NOT_REQUIRED"
    disclosure_type = None
    text = None
    reasons: list[str] = []

    if provenance.get("real_person_synthetic"):
        decision = "HUMAN_REVIEW"
        reasons.append("synthetic depiction of a real person")
    elif has_synthetic:
        field_rule = next((r for r in rules if r.action == "PLATFORM_FIELD_REQUIRED"), None)
        if field_rule:
            decision = "PLATFORM_FIELD_REQUIRED"
            disclosure_type = "PLATFORM_AI_FIELD"
            reasons.append(f"{platform} requires the platform AI/altered-content field ({field_rule.rule_id})")
        elif any(r.action in ("DISCLOSE", "REQUIRED") for r in rules):
            decision = "REQUIRED"
            disclosure_type = "IN_CONTENT"
        else:
            decision = "RECOMMENDED"
            disclosure_type = "IN_CONTENT"
        text = _ALTERED_KO if provenance.get("materially_altered") else _SYNTH_KO
    elif any_ai and rules:
        decision = "RECOMMENDED"
        disclosure_type = "IN_CONTENT"
        text = _SYNTH_KO
        reasons.append("AI-assisted content; platform encourages transparency")

    if stale and decision in ("NOT_REQUIRED", "RECOMMENDED") and any_ai:
        decision = "HUMAN_REVIEW"
        reasons.append("platform synthetic-media policy registry is stale — verify before auto-publish")

    return {"decision": decision, "disclosure_type": disclosure_type, "text": text,
            "reasons": reasons, "policy_stale": stale,
            "policy_version": _policy.POLICY_REGISTRY_VERSION}


_DISCLOSURE_MARKERS = ("AI가 생성", "AI가 합성", "합성하여 제작", "AI-generated", "synthetic",
                       "altered content", "AI info", "AIGC")


def assert_not_stripped(before_meta: dict, after_meta: dict) -> list[str]:
    """§34 — a natural-writing / platform-adapt / publisher step must not drop a
    disclosure that was set. Returns violation strings (empty = OK)."""
    v: list[str] = []
    for k in ("disclosure_required", "disclosure_type", "ai_generated",
              "synthetic_voice", "synthetic_video", "synthetic_image", "materially_altered"):
        b = bool(before_meta.get(k))
        a = bool(after_meta.get(k))
        if b and not a:
            v.append(f"disclosure flag '{k}' was removed downstream")
    bt = (before_meta.get("disclosure_text") or "").strip()
    at = (after_meta.get("disclosure_text") or "").strip()
    if bt and not at:
        v.append("disclosure_text was cleared downstream")
    return v


def strip_disclosure_from_text_guard(original_text: str, new_text: str) -> bool:
    """True if a disclosure sentence present in `original_text` is missing from
    `new_text` (used to block a naturalness/adaptation rewrite that removed it)."""
    had = any(m in (original_text or "") for m in _DISCLOSURE_MARKERS)
    has = any(m in (new_text or "") for m in _DISCLOSURE_MARKERS)
    return had and not has
