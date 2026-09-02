"""Claim governance (§47-§58, §69-§72) — provenance, statistic/quote/temporal
validation, fact↔visual mismatch. Deterministic.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

_NUM = re.compile(r"-?\d[\d,]*\.?\d*\s*(?:%|퍼센트|배|억|만|천|원|달러|명|건|위)?")
_STAT_NUM = re.compile(r"\d[\d,]*\.?\d*\s*(?:%|퍼센트|배)")
_OPINION = ("전문가들은", "라고 본다", "일 것이다", "할 것으로 보인다", "전망된다", "예상된다",
            "반드시", "분명히", "확실히", "틀림없이", "should", "will definitely", "must be")
_PREDICTION = ("앞으로", "향후", "곧", "2030년까지", "미래에", "내년에는")
_QUOTE = re.compile(r"[\"“”'’]([^\"“”'’]{6,})[\"“”'’]\s*(?:라고|—|-|,)?\s*(?:말했|밝혔|전했|said)")
_TIME_SENSITIVE = ("가격", "순위", "직책", "대표", "회장", "시가총액", "환율", "금리",
                   "출시", "규정", "법", "정책", "스펙", "버전", "최신")
_ADVERT = ("최고", "1위", "유일", "무조건", "100%", "완벽", "리스크 없", "guaranteed",
           "risk free", "best ever")


def classify_claim(text: str) -> str:
    t = text or ""
    if _QUOTE.search(t):
        return "QUOTE"
    if _STAT_NUM.search(t):
        return "STATISTIC"
    if any(a in t for a in _ADVERT):
        return "ADVERTISEMENT"
    if any(p in t for p in _PREDICTION):
        return "PREDICTION"
    if any(o in t for o in _OPINION):
        return "OPINION"
    if _NUM.search(t):
        return "FACT"
    return "FACT"


def stat_numbers(text: str) -> set[str]:
    return {m.group(0).replace(" ", "") for m in _STAT_NUM.finditer(text or "")}


def all_numbers(text: str) -> set[str]:
    return {m.group(0).strip().replace(" ", "") for m in _NUM.finditer(text or "") if any(c.isdigit() for c in m.group(0))}


def validate_statistic(claim: str, *, usable_fact_texts: list[str],
                       chart_values: list | None = None) -> dict:
    """A statistic must trace to a verified fact; a chart backing it must use the
    SAME number as the script (§52, §130)."""
    nums = stat_numbers(claim)
    if not nums:
        return {"status": "OK", "reason": "no statistic"}
    fact_nums: set[str] = set()
    for f in usable_fact_texts:
        fact_nums |= stat_numbers(f) | all_numbers(f)
    unbacked = {n for n in nums if n not in fact_nums and n.rstrip("%배") not in {x.rstrip("%배") for x in fact_nums}}
    if unbacked:
        return {"status": "UNSUPPORTED", "reason": f"statistic(s) not traceable to a verified fact: {sorted(unbacked)}"}
    if chart_values:
        chart_nums = {str(v).replace(" ", "") for v in chart_values}
        script_bare = {n.rstrip("%배 ") for n in nums}
        chart_bare = {c.rstrip("%배 ") for c in chart_nums}
        if not (script_bare & chart_bare):
            return {"status": "MISMATCH",
                    "reason": f"chart values {sorted(chart_bare)} do not match script number(s) {sorted(script_bare)}"}
    return {"status": "OK"}


def validate_quote(claim: str, *, source_ids: list[str]) -> dict:
    if not _QUOTE.search(claim or ""):
        return {"status": "OK", "reason": "no quote"}
    if not source_ids:
        return {"status": "UNSUPPORTED", "reason": "direct quote with no source attribution"}
    return {"status": "OK"}


def validate_opinion_as_fact(claim: str) -> dict:
    t = claim or ""
    has_opinion_marker = any(o in t for o in _OPINION) or any(p in t for p in _PREDICTION)
    stated_as_fact = has_opinion_marker and not any(
        h in t for h in ("일 수도", "가능성", "전망", "의견", "라고 보는 시각", "추정", "예측", "~라는 분석"))
    if stated_as_fact and any(x in t for x in ("반드시", "분명히", "확실히", "틀림없이", "will definitely")):
        return {"status": "OPINION_AS_FACT",
                "reason": "prediction/opinion phrased as certainty — soften or attribute"}
    return {"status": "OK"}


def temporal_validity(claim: str, *, verified_at: datetime | None,
                      max_age_days: int = 180, event_status: str = "") -> dict:
    t = claim or ""
    sensitive = any(k in t for k in _TIME_SENSITIVE) or bool(_STAT_NUM.search(t))
    if not sensitive:
        return {"status": "OK"}
    if event_status in ("DEVELOPING", "UNKNOWN"):
        return {"status": "STALE", "reason": f"time-sensitive claim on a {event_status} event — recheck / human review"}
    if event_status in ("CORRECTED", "RETRACTED"):
        return {"status": "STALE", "reason": f"source status is {event_status}"}
    if verified_at is None:
        return {"status": "STALE", "reason": "time-sensitive claim with no verified_at"}
    va = verified_at.replace(tzinfo=timezone.utc) if verified_at.tzinfo is None else verified_at
    age = (datetime.now(timezone.utc) - va).days
    if age > max_age_days:
        return {"status": "STALE", "reason": f"verified {age}d ago (> {max_age_days}d) — recheck before publish"}
    return {"status": "OK"}


def govern_claims(*, script_body: str, usable_fact_texts: list[str],
                  fact_source_map: dict | None = None, chart_values_by_claim: dict | None = None,
                  claim_verified_at: dict | None = None, event_status_by_claim: dict | None = None,
                  ) -> dict:
    """Split the script into sentences, classify + validate each. Returns a
    per-claim table + a rollup status."""
    fact_source_map = fact_source_map or {}
    chart_values_by_claim = chart_values_by_claim or {}
    claim_verified_at = claim_verified_at or {}
    event_status_by_claim = event_status_by_claim or {}

    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+|\n+", script_body or "") if s.strip()]
    rows: list[dict] = []
    worst = "OK"
    order = {"OK": 0, "STALE": 1, "OPINION_AS_FACT": 1, "UNSUPPORTED": 2, "MISMATCH": 3}
    for i, sent in enumerate(sentences):
        ctype = classify_claim(sent)
        checks: list[dict] = []
        if ctype == "STATISTIC":
            checks.append(validate_statistic(sent, usable_fact_texts=usable_fact_texts,
                                             chart_values=chart_values_by_claim.get(str(i))))
        if ctype == "QUOTE":
            checks.append(validate_quote(sent, source_ids=fact_source_map.get(str(i), [])))
        if ctype in ("OPINION", "PREDICTION", "FACT"):
            checks.append(validate_opinion_as_fact(sent))
        checks.append(temporal_validity(sent, verified_at=claim_verified_at.get(str(i)),
                                        event_status=event_status_by_claim.get(str(i), "")))
        status = "OK"
        for c in checks:
            if order.get(c["status"], 0) > order.get(status, 0):
                status = c["status"]
        if order.get(status, 0) > order.get(worst, 0):
            worst = status
        rows.append({"index": i, "text": sent[:160], "claim_type": ctype, "status": status,
                     "checks": [c for c in checks if c["status"] != "OK"]})
    decision = {"OK": "ALLOW", "STALE": "HUMAN_REVIEW", "OPINION_AS_FACT": "FIX_REQUIRED",
                "UNSUPPORTED": "FIX_REQUIRED", "MISMATCH": "BLOCK"}[worst]
    return {"rollup": worst, "decision": decision,
            "issues": [r for r in rows if r["status"] != "OK"], "n_claims": len(rows)}
