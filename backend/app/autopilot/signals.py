from __future__ import annotations

import re
from datetime import timedelta

# Pure sub-score functions (0..100). Input = a RawTrendEvent-ish dict with
# engagement_signals carrying `interest_series`, `shape`, `risk_hint`,
# `competition_hint`, `evergreen`, plus source_metrics.

_TREND_TYPE_TTL = {
    "BREAKING": timedelta(hours=12),
    "FAST_TREND": timedelta(hours=36),
    "NORMAL_TREND": timedelta(days=5),
    "SEASONAL": timedelta(days=21),
    "EVERGREEN": timedelta(days=365),
    "RECURRING": timedelta(days=30),
}

_RISK_CATEGORIES = {
    "MEDICAL": ["혈압", "약", "예방접종", "질환", "증상", "복용", "diagnos", "치료"],
    "FINANCIAL": ["투자", "수익", "코인", "비트코인", "etf", "대출", "금리", "세금", "절세", "보조금", "지원금", "월세"],
    "LEGAL": ["계약", "사기", "판결", "소송", "법", "규정", "과세", "분쟁"],
    "POLITICAL": ["여론조사", "정당", "정부", "정책 논란"],
    "ELECTION": ["총선", "대선", "선거", "후보"],
    "MINORS": ["청소년", "미성년", "학생"],
    "TRAGEDY": ["사고", "참사", "사망", "재난"],
    "COPYRIGHT": ["저작권", "무단"],
    "BREAKING_NEWS": ["속보", "긴급"],
}


def _series(sig: dict) -> dict:
    return sig.get("interest_series", {}) or {}


def velocity_score(sig: dict) -> float:
    s = _series(sig)
    if not s:
        return 50.0
    short = (s.get("1h", 0) + s.get("6h", 0)) / 2
    long = (s.get("7d", 0) + s.get("30d", 0)) / 2 or 0.01
    ratio = short / long
    return round(max(0.0, min(100.0, 50.0 + (ratio - 1.0) * 55.0)), 2)


def acceleration_score(sig: dict) -> float:
    s = _series(sig)
    if not s:
        return 50.0
    d7 = s.get("3d", 0) - s.get("7d", 0)
    d1 = s.get("6h", 0) - s.get("24h", 0)
    d6 = s.get("1h", 0) - s.get("6h", 0)
    accel = (d6 - d1) + (d1 - d7)
    return round(max(0.0, min(100.0, 50.0 + accel * 220.0)), 2)


def trend_status(sig: dict) -> str:
    s = _series(sig)
    if not s:
        return "UNKNOWN"
    short = (s.get("1h", 0) + s.get("6h", 0)) / 2
    mid = s.get("24h", 0)
    long = (s.get("7d", 0) + s.get("30d", 0)) / 2 or 0.01
    if short > long * 2.5 and short > mid * 1.4:
        return "BREAKOUT"
    if short > long * 1.4:
        return "ACCELERATING" if short > mid else "RISING"
    if long > short * 1.8:
        return "DECLINING"
    if sig.get("competition_hint") == "high" and short > 0.6:
        return "SATURATED"
    return "STABLE"


def trend_type(sig: dict) -> str:
    shape = (sig.get("shape") or "").lower()
    if sig.get("evergreen"):
        return "EVERGREEN"
    return {
        "breakout": "BREAKING", "rising": "FAST_TREND", "declining": "NORMAL_TREND",
        "seasonal": "SEASONAL", "stable": "NORMAL_TREND", "evergreen": "EVERGREEN",
    }.get(shape, "NORMAL_TREND")


def ttl_for(ttype: str) -> timedelta:
    return _TREND_TYPE_TTL.get(ttype, timedelta(days=5))


def freshness_score(sig: dict) -> float:
    ttype = trend_type(sig)
    base = {"BREAKING": 95, "FAST_TREND": 82, "SEASONAL": 70, "NORMAL_TREND": 60,
            "RECURRING": 55, "EVERGREEN": 45}.get(ttype, 55)
    st = trend_status(sig)
    if st == "DECLINING":
        base -= 25
    if st in ("BREAKOUT", "ACCELERATING"):
        base += 8
    return float(max(0, min(100, base)))


def competition_score(sig: dict, metrics: dict) -> float:
    hint = {"low": 25, "mid": 55, "high": 85}.get(sig.get("competition_hint", "mid"), 55)
    uploads = metrics.get("recent_uploads_7d", 0)
    upl = min(30.0, uploads / 3.0)
    return round(min(100.0, hint * 0.7 + upl), 2)


def saturation_score(sig: dict, metrics: dict) -> float:
    comp = competition_score(sig, metrics)
    st = trend_status(sig)
    trend_high = (_series(sig).get("6h", 0) + _series(sig).get("24h", 0)) / 2 * 100
    sat = comp * 0.55 + trend_high * 0.35
    if st == "SATURATED":
        sat += 15
    if st in ("BREAKOUT",):
        sat -= 15
    return round(max(0.0, min(100.0, sat)), 2)


def risk_classify(topic: str, sig: dict) -> tuple[str, list[str], float]:
    low = topic.lower()
    cats = [c for c, kws in _RISK_CATEGORIES.items() if any(k in low for k in kws)]
    hint = (sig.get("risk_hint") or "LOW").upper()
    if hint not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        hint = "LOW"
    level = hint
    if {"ELECTION", "MEDICAL"} & set(cats):
        level = "HIGH" if level in ("LOW", "MEDIUM") else level
    if {"TRAGEDY", "MINORS"} & set(cats):
        level = "CRITICAL"
    if "BREAKING_NEWS" in cats and level == "LOW":
        level = "MEDIUM"
    score = {"LOW": 12, "MEDIUM": 40, "HIGH": 72, "CRITICAL": 95}[level]
    return level, cats, float(score)


def difficulty_class(topic: str, sig: dict) -> str:
    low = topic.lower()
    hard = 0
    if any(k in low for k in ("판결", "데이터", "분석", "통계", "여론조사", "시나리오")):
        hard += 1
    if any(k in low for k in ("최신", "속보", "논란", "동향")):
        hard += 1
    if risk_classify(topic, sig)[0] in ("HIGH", "CRITICAL"):
        hard += 1
    if any(k in low for k in ("비교", "가이드", "총정리")):
        hard += 1
    return ["LOW", "MEDIUM", "HIGH", "VERY_HIGH"][min(3, hard)]


def natural_content_score(topic: str, sig: dict) -> float:
    """Can this topic yield genuinely non-slop content? Needs concrete examples,
    visuals, data, comparison, a human angle."""
    low = topic.lower()
    score = 45.0
    if any(k in low for k in ("사례", "실제", "데이터", "비교", "체크리스트", "순위", "가이드", "루틴")):
        score += 22
    if any(k in low for k in ("왜", "이유", "타이밍", "판단", "오해", "착각")):
        score += 14
    if sig.get("evergreen"):
        score += 8
    if difficulty_class(topic, sig) == "VERY_HIGH":
        score -= 12
    # pure single-fact / listicle-of-nothing risk
    if re.fullmatch(r"[\w가-힣]{1,6}", topic.strip()):
        score -= 30
    return float(max(0.0, min(100.0, score)))


def production_cost_estimate(topic: str, sig: dict, *, base_usd: float = 0.0) -> tuple[float, float]:
    """Return (estimated_usd, production_cost_score 0..100 where high = cheap)."""
    diff = difficulty_class(topic, sig)
    scenes = {"LOW": 5, "MEDIUM": 6, "HIGH": 8, "VERY_HIGH": 10}[diff]
    # mock providers are $0; model a nominal projected spend for the allocator
    nominal = 0.15 + scenes * 0.03 + (0.2 if "차트" in topic or "데이터" in topic else 0.0)
    cost_score = max(0.0, 100.0 - (nominal - 0.2) * 120.0)
    return round(nominal, 4), round(min(100.0, cost_score), 2)


def fact_availability_score(result_count: int, *, min_reliable: int = 3) -> float:
    if result_count >= min_reliable * 3:
        return 90.0
    if result_count >= min_reliable:
        return 65.0
    if result_count >= 1:
        return 35.0
    return 10.0
