from __future__ import annotations

from app.config import get_settings

# Opportunity formula. All inputs are 0..100. For "cost", "competition",
# "saturation", "fatigue", "risk", "difficulty" a HIGHER raw value is WORSE, so
# they enter the weighted sum inverted (100 - x).
FORMULA_VERSION_DEFAULT = "opportunity_formula_v1"

_INVERT = {"competition", "saturation", "fatigue", "risk", "difficulty", "production_cost_raw"}

# objective -> {dimension: weight}. Dimensions not listed get weight 0.
_WEIGHTS: dict[str, dict[str, float]] = {
    "VIEWS": {"trend": 0.22, "velocity": 0.16, "acceleration": 0.08, "freshness": 0.10,
              "audience_fit": 0.14, "historical": 0.10, "competition": 0.08,
              "originality": 0.06, "natural_content": 0.06},
    "FOLLOWERS": {"audience_fit": 0.26, "historical": 0.18, "trend": 0.12, "velocity": 0.08,
                  "originality": 0.10, "natural_content": 0.10, "competition": 0.08,
                  "fatigue": 0.08},
    "REVENUE": {"revenue": 0.30, "audience_fit": 0.16, "historical": 0.14, "trend": 0.10,
                "natural_content": 0.10, "competition": 0.08, "fact_availability": 0.06,
                "risk": 0.06},
    "PROFIT": {"profit": 0.30, "revenue": 0.16, "production_cost": 0.16, "historical": 0.12,
               "audience_fit": 0.10, "competition": 0.08, "risk": 0.08},
    "BRAND": {"natural_content": 0.20, "fact_availability": 0.18, "audience_fit": 0.16,
              "originality": 0.14, "historical": 0.10, "risk": 0.12, "freshness": 0.10},
    "BALANCED": {"trend": 0.14, "velocity": 0.10, "freshness": 0.08, "audience_fit": 0.14,
                 "historical": 0.12, "revenue": 0.08, "originality": 0.08,
                 "natural_content": 0.10, "competition": 0.08, "risk": 0.05,
                 "production_cost": 0.03},
}

# per-platform tilt: which dimensions each platform rewards more/less
_PLATFORM_TILT: dict[str, dict[str, float]] = {
    "youtube_long": {"natural_content": 1.3, "fact_availability": 1.3, "freshness": 0.8},
    "youtube_shorts": {"velocity": 1.3, "trend": 1.2, "natural_content": 0.9},
    "tiktok": {"velocity": 1.4, "acceleration": 1.3, "trend": 1.2, "fact_availability": 0.7},
    "instagram_reel": {"natural_content": 1.2, "originality": 1.2},
    "instagram_carousel": {"natural_content": 1.2, "fact_availability": 1.1, "velocity": 0.7},
    "threads": {"freshness": 1.2, "originality": 1.2, "velocity": 1.1},
    "x": {"freshness": 1.4, "velocity": 1.2, "natural_content": 0.8},
    "pinterest": {"historical": 1.2, "natural_content": 1.1, "velocity": 0.6, "freshness": 0.6},
    "linkedin": {"fact_availability": 1.3, "natural_content": 1.2, "audience_fit": 1.1,
                 "velocity": 0.7},
    "naver_blog": {"fact_availability": 1.2, "natural_content": 1.1, "velocity": 0.6},
}


def objective_weights(objective: str) -> dict[str, float]:
    return dict(_WEIGHTS.get(objective.upper(), _WEIGHTS["BALANCED"]))


def _weighted(dims: dict[str, float], weights: dict[str, float]) -> float:
    total_w = sum(weights.values()) or 1.0
    acc = 0.0
    for k, w in weights.items():
        raw = dims.get(k)
        if raw is None:
            total_w -= w
            continue
        val = (100.0 - raw) if k in _INVERT else raw
        acc += w * val
    return round(acc / (total_w or 1.0), 2)


def score_opportunity(dims: dict[str, float], *, objective: str,
                      dedup_penalty: float = 0.0,
                      formula_version: str | None = None) -> dict:
    fv = formula_version or get_settings().opportunity_formula_version or FORMULA_VERSION_DEFAULT
    weights = objective_weights(objective)
    base = _weighted(dims, weights)
    final = round(max(0.0, min(100.0, base + dedup_penalty)), 2)

    reasons: list[str] = []
    if dims.get("velocity", 0) >= 65 or dims.get("acceleration", 0) >= 65:
        reasons.append("최근 관심 상승세")
    if dims.get("historical", 0) >= 62:
        reasons.append("과거 유사 콘텐츠 성과 양호")
    if dims.get("audience_fit", 0) >= 62:
        reasons.append("우리 오디언스 적합도 높음")
    if dims.get("competition", 100) <= 45:
        reasons.append("동일 앵글 경쟁 낮음")
    if dims.get("production_cost", 0) >= 65:
        reasons.append("예상 제작비 낮음")
    if dims.get("fact_availability", 0) >= 60:
        reasons.append("검증 가능한 자료 충분")
    if dims.get("natural_content", 0) >= 60:
        reasons.append("자연스러운 콘텐츠로 만들기 좋은 주제")
    if dedup_penalty <= -12:
        reasons.append("최근 유사 주제 게시됨(중복 감점)")
    if dims.get("risk", 0) >= 60:
        reasons.append("리스크 높음 — 승인 필요 가능")

    return {
        "opportunity_score": final,
        "formula_version": fv,
        "objective": objective.upper(),
        "components": {k: dims.get(k) for k in weights},
        "all_dimensions": dims,
        "dedup_penalty": dedup_penalty,
        "reasons": reasons,
    }


def platform_scores(dims: dict[str, float], *, objective: str,
                    platforms: list[str], dedup_penalty: float = 0.0) -> dict[str, float]:
    weights = objective_weights(objective)
    out: dict[str, float] = {}
    for p in platforms:
        tilt = _PLATFORM_TILT.get(p, {})
        pw = {k: w * tilt.get(k, 1.0) for k, w in weights.items()}
        out[p] = round(max(0.0, min(100.0, _weighted(dims, pw) + dedup_penalty)), 2)
    return out
