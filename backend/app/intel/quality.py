"""ReferenceQualityAnalyzer + deduplication.

Data volume is not quality (spec §AF). A low-scoring reference gets a low
`learning_weight`, not a veto — except duplicates and rights problems.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from app.analytics.embedding import cosine, embed
from app.governance.originality import text_similarity

_WORD = re.compile(r"[\w가-힣]+")
_YEAR = re.compile(r"\b(20\d{2})\b")


def content_hash(text: str) -> str:
    norm = " ".join(_WORD.findall((text or "").lower()))
    return hashlib.sha256(norm.encode()).hexdigest()


def text_fingerprint(text: str, *, k: int = 64) -> str:
    """cheap simhash-ish fingerprint for near-duplicate detection."""
    toks = _WORD.findall((text or "").lower())
    if not toks:
        return "0" * 16
    bits = [0] * k
    for t in set(toks):
        h = int(hashlib.md5(t.encode()).hexdigest(), 16)
        for i in range(k):
            bits[i] += 1 if (h >> i) & 1 else -1
    val = 0
    for i in range(k):
        if bits[i] > 0:
            val |= (1 << i)
    return f"{val:016x}"


def _hamming_hex(a: str, b: str) -> int:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except ValueError:
        return 64


def freshness(published_at: str, updated_at: str = "") -> float:
    src = updated_at or published_at or ""
    m = _YEAR.search(src)
    if not m:
        return 0.5   # unknown -> neutral, not 0
    year = int(m.group(1))
    now = datetime.now(timezone.utc).year
    age = max(0, now - year)
    return round(max(0.1, 1.0 - age * 0.18), 3)


def _density(text: str) -> float:
    sents = [s for s in re.split(r"(?<=[.!?…])\s+|\n+", text or "") if len(s.strip()) > 10]
    if not sents:
        return 0.0
    nums = len(re.findall(r"\d", text or ""))
    uniq = len(set(_WORD.findall((text or "").lower())))
    return round(min(1.0, (uniq / max(1, len(_WORD.findall(text or "")))) * 0.7
                     + min(1.0, nums / max(1, len(text or ""))) * 3), 3)


def _noise(text: str) -> float:
    if not text:
        return 1.0
    junk = len(re.findall(r"(cookie|subscribe|advertisement|점검 중|로그인|©|\|\s*Menu)", text, re.I))
    caps = sum(1 for c in text if c.isupper())
    return round(min(1.0, junk * 0.08 + (caps / max(1, len(text))) * 2), 3)


def source_quality(doc: dict, source_type: str) -> float:
    score = {
        "OFFICIAL_DOCUMENT": 0.9, "NEWS_ARTICLE": 0.75, "GITHUB_REPOSITORY": 0.8,
        "GITHUB_FILE": 0.75, "PDF": 0.75, "BLOG": 0.6, "WEB_PAGE": 0.55,
        "PRODUCT_PAGE": 0.5, "YOUTUBE": 0.6, "VIDEO_PAGE": 0.55, "SOCIAL_POST": 0.4,
        "UNKNOWN": 0.3,
    }.get(source_type, 0.4)
    if doc.get("author"):
        score += 0.05
    if doc.get("source_references"):
        score += 0.05
    if doc.get("published_at"):
        score += 0.03
    return round(min(1.0, score), 3)


def analyze_quality(doc: dict, *, source_type: str, topic: str = "",
                    injection_severity: str = "NONE") -> dict:
    """DataQualityScore. Returns component scores + an aggregate + learning_weight."""
    text = doc.get("main_text", "") or ""
    sq = source_quality(doc, source_type)
    density = _density(text)
    noise = _noise(text)
    fresh = freshness(doc.get("published_at", ""), doc.get("updated_at", ""))
    rel = relevance(text + " " + doc.get("title", ""), topic) if topic else 0.5
    novelty = round(min(1.0, len(set(_WORD.findall(text.lower()))) / 400), 3)
    technical = round(min(1.0, len(re.findall(
        r"(algorithm|dataset|benchmark|architecture|framework|정확도|성능|수치)", text, re.I)) / 8), 3)

    penalty = 0.0
    if injection_severity == "HIGH":
        penalty += 0.4
    elif injection_severity == "MEDIUM":
        penalty += 0.15
    if len(text) < 300:
        penalty += 0.25

    agg = max(0.0, round(
        0.30 * sq + 0.20 * density + 0.15 * rel + 0.10 * fresh
        + 0.10 * novelty + 0.10 * (1 - noise) + 0.05 * technical - penalty, 3))
    weight = round(max(0.05, min(1.0, agg)), 3)
    return {
        "source_quality": sq, "information_density": density, "relevance": rel,
        "novelty": novelty, "freshness": fresh, "noise": noise,
        "technical_usefulness": technical, "duplicate_risk": 0.0,
        "aggregate": agg, "learning_weight": weight,
        "low_value": agg < 0.35,
    }


def relevance(text: str, topic: str) -> float:
    if not topic:
        return 0.5
    return round(max(0.0, cosine(embed(text[:4000]), embed(topic))), 3)


# --------------------------------------------------------------------- #
#  Deduplication (spec §AG)
# --------------------------------------------------------------------- #

def duplicate_of(new_doc: dict, *, canonical_url: str, existing: list[dict]) -> dict | None:
    """existing: [{id, canonical_url, content_hash, text_fingerprint, sim_vector,
    main_text}]. Returns the matched row + method, or None."""
    nh = content_hash(new_doc.get("main_text", ""))
    nfp = text_fingerprint(new_doc.get("main_text", ""))
    nvec = embed(new_doc.get("main_text", "")[:4000])
    for e in existing:
        if canonical_url and e.get("canonical_url") and canonical_url == e["canonical_url"]:
            return {"match_id": e.get("id"), "method": "canonical_url"}
        if e.get("content_hash") and e["content_hash"] == nh:
            return {"match_id": e.get("id"), "method": "content_hash"}
        if e.get("text_fingerprint") and _hamming_hex(nfp, e["text_fingerprint"]) <= 3:
            return {"match_id": e.get("id"), "method": "text_fingerprint"}
        ev = e.get("sim_vector")
        if ev and cosine(nvec, ev) >= 0.985:
            return {"match_id": e.get("id"), "method": "semantic"}
        if e.get("main_text"):
            sim = text_similarity(new_doc.get("main_text", "")[:6000], e["main_text"][:6000])
            if sim["combined"] >= 0.92:
                return {"match_id": e.get("id"), "method": "text_similarity",
                        "score": sim["combined"]}
    return None
