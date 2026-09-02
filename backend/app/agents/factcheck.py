"""Deterministic fact-check pre/post processing (Best-of-Breed audit — Fact Checker).

Atomic claim extraction, claim→source token mapping, cross-source agreement
count, temporal-marker extraction, and a confidence blend. The LLM still makes
the VERIFIED/CONTRADICTED call; this makes what it checks smaller and sharper and
hardens the confidence number. Pattern: Loki / SAFE / FactScore. No dependency.
"""
from __future__ import annotations

import re

_WORD = re.compile(r"[\w가-힣]+")
_STOP = {"그리고", "그러나", "하지만", "the", "a", "of", "및", "수", "것", "이", "가", "은", "는"}
# clause boundaries — split the whitespace that FOLLOWS a clause-ending connective
# so the connective (and its verb polarity) stays with the left-hand claim.
_SPLIT = re.compile(
    r"(?:(?<=었고)|(?<=았고)|(?<=였고)|(?<=하고)|(?<=이고)|(?<=되고)|(?<=하며)|(?<=되며)|(?<=으며)|"
    r"(?<=,)|(?<=;)|(?<=·)|(?<=、)|(?<=또한)|(?<=또는)|(?<=뿐만 아니라)|(?<= and also)|(?<= as well as))\s+"
)
_TEMPORAL = re.compile(
    r"(\d{4}\s*년|\d{4}-\d{2}|\d+\s*(?:년|개월|분기|주|일)\s*(?:전|후|간|동안|만에)|"
    r"최근|현재|올해|작년|지난해|향후|앞으로|당시|이전|이후|now|currently|recently|"
    r"in \d{4}|since \d{4})"
)


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP and len(w) > 1}


def atomic_claims(candidate_facts: list[dict], *, max_per_fact: int = 3) -> list[dict]:
    """Split each candidate fact into independently checkable atomic claims.

    A fact with no clause/conjunction boundary (the common case, and every mock
    fact) passes through unchanged. Each atomic claim keeps its parent's
    source_ids and records `derived_from`.
    """
    out: list[dict] = []
    for f in candidate_facts:
        text = (f.get("fact") or "").strip()
        if not text:
            continue
        parts = [p.strip(" .·,") for p in _SPLIT.split(text) if p and p.strip(" .·,")]
        # only treat as a real split if it produced >=2 parts each with substance
        parts = [p for p in parts if len(_tokens(p)) >= 2]
        if len(parts) < 2:
            out.append({**f, "fact": text, "atomic": False})
            continue
        for p in parts[:max_per_fact]:
            out.append({
                **f, "fact": p, "atomic": True, "derived_from": text,
                "source_ids": list(f.get("source_ids", [])),
            })
    return out


def checkworthy(claim: str) -> bool:
    """Skip verifying pure opinion / definitional / meta lines — spend the LLM
    budget on factual, consequential claims (Loki checkworthiness)."""
    t = (claim or "").strip()
    if len(_tokens(t)) < 3:
        return False
    opinion = ("생각한다", "느낀다", "같다", "듯하다", "아마", "개인적으로", "i think",
               "in my opinion", "arguably")
    if any(o in t.lower() for o in opinion) and not re.search(r"\d", t):
        return False
    return True


def agreement_count(claim: str, sources: list[dict]) -> int:
    """How many distinct sources share >=2 salient tokens with the claim."""
    ct = _tokens(claim)
    if not ct:
        return 0
    n = 0
    for s in sources:
        st = _tokens(f"{s.get('title', '')} {s.get('snippet', '')}")
        if len(ct & st) >= 2:
            n += 1
    return n


def temporal_markers(claim: str) -> list[str]:
    return [m.group(0).strip() for m in _TEMPORAL.finditer(claim or "")]


def blend_confidence(llm_confidence: float, *, agreement: int, has_sources: bool,
                     numeric_claim: bool = False, temporal: bool = False) -> float:
    """Combine the model's self-reported confidence with structural evidence:
    more independent agreeing sources -> higher; no sources -> capped low; a
    numeric/time-bound claim with no temporal marker -> small staleness penalty."""
    c = float(llm_confidence or 0.0)
    if not has_sources:
        return round(min(c, 0.3), 3)
    c = c * 0.7 + min(1.0, agreement / 3.0) * 0.3
    if numeric_claim and not temporal:
        c -= 0.05
    return round(max(0.0, min(0.98, c)), 3)


def enrich_facts(facts: list[dict], sources: list[dict]) -> list[dict]:
    """Post-process LLM fact verdicts: attach agreement_count + temporal markers,
    re-blend confidence, and downgrade a lone-source 'VERIFIED' to
    'PARTIALLY_VERIFIED' (no independent corroboration)."""
    out: list[dict] = []
    for f in facts:
        claim = f.get("fact", "")
        ag = agreement_count(claim, sources)
        tm = temporal_markers(claim)
        has_src = bool(f.get("source_ids"))
        conf = blend_confidence(f.get("confidence", 0.0), agreement=ag,
                                has_sources=has_src, numeric_claim=bool(re.search(r"\d", claim)),
                                temporal=bool(tm))
        status = f.get("status", "UNVERIFIED")
        note = f.get("reason", "")
        if status == "VERIFIED" and ag < 2 and has_src:
            status = "PARTIALLY_VERIFIED"
            note = (note + " · 단일 출처 — 교차 확인 부족").strip(" ·")
        out.append({**f, "status": status, "confidence": conf, "reason": note,
                    "agreement_count": ag, "temporal_markers": tm})
    return out
