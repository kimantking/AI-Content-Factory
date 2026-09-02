"""Deterministic hook post-processing (Best-of-Breed audit — Hook Agent).

Multi-candidate diversity, recent-hook similarity penalty, platform-aware
re-ranking, and a factual-exaggeration guard. The LLM generates the candidates;
this re-scores + prunes them. No dependency.
"""
from __future__ import annotations

import re

from app.analytics.embedding import cosine, embed

# absolute / superlative claims that need a matching verified fact to be allowed
_ABSOLUTE = (
    "역대 최고", "역대 최악", "사상 최초", "세계 최초", "무조건", "절대",
    "100%", "완벽하게", "모두가", "아무도", "전부", "항상", "언제나",
    "guaranteed", "never", "always", "everyone", "no one", "the best ever",
)
_NUM = re.compile(r"\d[\d,.%]*")
# numbers glued to a time unit ("3년간", "6개월") are spans, not statistics
_TIME_NUM = re.compile(r"\d[\d,. ]*\s*(?:년|개월|분기|주|일|시간|분|초|년간|개월간)")


def _stat_numbers(text: str) -> set[str]:
    stripped = _TIME_NUM.sub(" ", text or "")
    return set(_NUM.findall(stripped))
_PLATFORM_TILT = {
    "youtube_shorts": {"숫자": 1.2, "질문": 1.1, "긴장": 1.1},
    "tiktok": {"긴장": 1.2, "정보격차": 1.15, "숫자": 1.1},
    "youtube_long": {"질문": 1.15, "정보격차": 1.2, "긴장": 0.9},
    "instagram_reel": {"호기심": 1.15, "감정": 1.1},
    "threads": {"질문": 1.2, "의견": 1.15},
    "x": {"질문": 1.15, "긴장": 1.1},
    "linkedin": {"데이터": 1.25, "인사이트": 1.2, "긴장": 0.8},
}


def exaggeration_flags(text: str, usable_fact_texts: list[str]) -> list[str]:
    """Flag absolute/superlative language or a number not traceable to a verified
    fact. These are downweighted, not auto-removed (the copy may be fine)."""
    flags: list[str] = []
    low = text.lower()
    for phrase in _ABSOLUTE:
        if phrase in low:
            flags.append(f"absolute_claim:{phrase}")
    fact_nums = set()
    for f in usable_fact_texts:
        fact_nums.update(_stat_numbers(f))
    hook_nums = _stat_numbers(text)
    unbacked = hook_nums - fact_nums
    if unbacked:
        flags.append(f"unbacked_number:{sorted(unbacked)}")
    return flags


def _too_similar(a: str, b: str, *, threshold: float = 0.86) -> bool:
    return cosine(embed(a), embed(b)) >= threshold


def diversity_filter(hooks: list[dict], *, threshold: float = 0.93, min_keep: int = 3) -> list[dict]:
    """Drop near-duplicate hooks (keep the higher-scored of a similar pair), but
    never fall below `min_keep` candidates — pruning must not starve the picker."""
    ordered = sorted(hooks, key=lambda h: h.get("score", 0), reverse=True)
    kept: list[dict] = []
    dropped: list[dict] = []
    for h in ordered:
        if any(_too_similar(h.get("text", ""), k.get("text", ""), threshold=threshold) for k in kept):
            dropped.append(h)
            continue
        kept.append(h)
    while len(kept) < min_keep and dropped:
        kept.append(dropped.pop(0))
    return kept


def score_hooks(hooks: list[dict], *, platform: str | None, recent_hook_texts: list[str],
                usable_fact_texts: list[str]) -> list[dict]:
    """Re-score each hook: base LLM score, minus recent-similarity, minus
    exaggeration, times a platform tilt. Adds `adjusted_score` + `flags`."""
    tilt = _PLATFORM_TILT.get((platform or "").lower(), {})
    out: list[dict] = []
    for h in hooks:
        text = h.get("text", "")
        style = h.get("style", "")
        base = float(h.get("score", 0.0))
        # recent similarity penalty
        recent_pen = 0.0
        for rt in recent_hook_texts:
            sim = cosine(embed(text), embed(rt))
            if sim > 0.72:
                recent_pen = max(recent_pen, (sim - 0.72) * 1.2)
        flags = exaggeration_flags(text, usable_fact_texts)
        exagg_pen = 0.12 * len(flags)
        mult = 1.0
        for kw, m in tilt.items():
            if kw in style or kw in text:
                mult *= m
        adjusted = max(0.0, (base - recent_pen - exagg_pen) * mult)
        out.append({**h, "adjusted_score": round(adjusted, 4),
                    "flags": flags, "recent_penalty": round(recent_pen, 4)})
    out.sort(key=lambda h: h.get("adjusted_score", 0), reverse=True)
    return out


def refine(hooks: list[dict], *, platform: str | None, recent_hook_texts: list[str],
           usable_fact_texts: list[str]) -> tuple[list[dict], dict]:
    diverse = diversity_filter(hooks)
    scored = score_hooks(diverse, platform=platform, recent_hook_texts=recent_hook_texts,
                         usable_fact_texts=usable_fact_texts)
    chosen = scored[0] if scored else {"text": "", "style": "", "score": 0, "adjusted_score": 0}
    meta = {
        "generated": len(hooks), "after_diversity": len(diverse),
        "chosen_flags": chosen.get("flags", []),
        "any_exaggeration": any(h.get("flags") for h in scored),
    }
    return scored, {"chosen": chosen, **meta}
