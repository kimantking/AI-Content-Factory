"""Deterministic research helpers (Best-of-Breed agent audit — Research Agent).

Query decomposition, source diversity / domain-authority ranking, a coverage-based
stopping criterion, and a research-budget object. All pure functions — the LLM
still does the synthesis. Patterns from gpt-researcher / STORM / local-deep-
researcher; no dependency added.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.analytics.embedding import cosine, embed

_STOP = {"그리고", "그러나", "하지만", "the", "a", "of", "to", "및", "수", "것", "이", "가"}
_WORD = re.compile(r"[\w가-힣]+")

# angle templates for the FIRST research pass — decompose one topic into a small
# set of complementary sub-queries hitting different evidence angles.
_ANGLES = [
    "{topic}",
    "{topic} 통계 데이터 최신 수치",
    "{topic} 사례 실제 예시",
    "{topic} 반대 의견 비판 한계",
    "{topic} 원인 배경 이유",
]

# rough domain-authority tiers for source ranking (higher = more trusted).
_AUTHORITY = {
    ".gov": 1.0, ".go.kr": 1.0, ".edu": 0.95, ".ac.kr": 0.95,
    ".org": 0.75, "who.int": 0.95, "oecd.org": 0.9, "worldbank.org": 0.9,
    "wikipedia.org": 0.6, "naver.com": 0.55, "medium.com": 0.4, "blog": 0.3,
    "tistory.com": 0.3, "brunch.co.kr": 0.35,
}


@dataclass
class ResearchBudget:
    max_queries: int = 4
    max_fix_passes: int = 2
    max_sources: int = 8
    queries_used: int = 0
    fix_passes_used: int = 0

    def can_query(self) -> bool:
        return self.queries_used < self.max_queries

    def spend_query(self, n: int = 1) -> None:
        self.queries_used += n


def expand_queries(topic: str, keywords: list[str] | None = None, *, limit: int = 3) -> list[str]:
    """Decompose the topic into `limit` complementary sub-queries. Deterministic,
    order-stable. The first is always the bare topic."""
    kws = [k for k in (keywords or []) if k and k.lower() not in _STOP][:2]
    out: list[str] = []
    for tmpl in _ANGLES:
        q = tmpl.format(topic=topic)
        if q not in out:
            out.append(q)
        if len(out) >= limit:
            break
    # fold a strong keyword into one slot if we have room and a distinct keyword
    if kws and len(out) < limit + 1:
        extra = f"{topic} {kws[0]}"
        if extra not in out:
            out.append(extra)
    return out[:max(1, limit)]


def _domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _authority(url: str) -> float:
    d = _domain(url)
    for frag, score in _AUTHORITY.items():
        if frag in d or frag in url.lower():
            return score
    return 0.5


def merge_and_rank(result_groups: list[list], *, topic: str, limit: int = 8) -> list:
    """Merge results from several sub-queries, drop URL duplicates, then rank by
    domain authority + topical match + freshness, and enforce domain diversity
    (no more than 2 from the same domain in the top slots)."""
    topic_vec = embed(topic)
    seen_urls: set[str] = set()
    scored: list[tuple[float, object]] = []
    for group in result_groups:
        for r in group:
            url = getattr(r, "url", "") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = getattr(r, "title", "") or ""
            snip = getattr(r, "snippet", "") or ""
            rel = max(0.0, cosine(topic_vec, embed(f"{title} {snip}")))
            auth = _authority(url)
            pub = getattr(r, "published_at", "") or ""
            fresh = 0.6
            m = re.match(r"(\d{4})-(\d{2})", str(pub))
            if m:
                y = int(m.group(1))
                fresh = 1.0 if y >= 2026 else 0.8 if y >= 2025 else 0.5
            score = 0.45 * auth + 0.35 * rel + 0.20 * fresh
            scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    out: list = []
    per_domain: dict[str, int] = {}
    overflow: list = []
    for _s, r in scored:
        d = _domain(getattr(r, "url", ""))
        if per_domain.get(d, 0) >= 2:
            overflow.append(r)
            continue
        per_domain[d] = per_domain.get(d, 0) + 1
        out.append(r)
        if len(out) >= limit:
            break
    for r in overflow:                       # backfill if diversity cap left us short
        if len(out) >= limit:
            break
        out.append(r)
    return out


def source_diversity(results: list) -> float:
    """0..1 — share of distinct domains among the sources."""
    if not results:
        return 0.0
    domains = {_domain(getattr(r, "url", "")) for r in results}
    return round(len(domains) / len(results), 3)


def coverage_score(candidate_facts: list[dict], sources: list) -> float:
    """Cheap 'do we have enough?' signal: verified-fact count vs a target, scaled
    by source diversity. Used as an additional stopping criterion beyond the
    fact-score gate."""
    n_facts = len([f for f in candidate_facts if f.get("fact")])
    div = source_diversity(sources)
    fact_component = min(1.0, n_facts / 4.0)
    return round(0.6 * fact_component + 0.4 * div, 3)


def find_contradictions(candidate_facts: list[dict]) -> list[dict]:
    """Flag pairs of candidate facts that look like they disagree — same subject
    tokens but an opposite polarity word. Deterministic, conservative."""
    neg = ("아니", "없", "감소", "하락", "줄어", "반대", "않", "unlikely", "false", "no ")
    pos = ("맞", "있", "증가", "상승", "늘어", "찬성", "true", "yes ")
    out: list[dict] = []
    facts = [f for f in candidate_facts if f.get("fact")]
    for i in range(len(facts)):
        for j in range(i + 1, len(facts)):
            a, b = facts[i]["fact"], facts[j]["fact"]
            ta = {w for w in _WORD.findall(a.lower()) if w not in _STOP and len(w) > 1}
            tb = {w for w in _WORD.findall(b.lower()) if w not in _STOP and len(w) > 1}
            if len(ta & tb) < 2:
                continue
            a_neg = any(k in a for k in neg)
            b_neg = any(k in b for k in neg)
            a_pos = any(k in a for k in pos)
            b_pos = any(k in b for k in pos)
            if (a_neg and b_pos) or (a_pos and b_neg):
                out.append({"a": a, "b": b, "shared_terms": sorted(ta & tb)[:4]})
    return out
