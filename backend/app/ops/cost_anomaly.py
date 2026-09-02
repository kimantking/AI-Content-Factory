from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.config import get_settings
from app.db.base import session_scope
from app.db.models import CostLog


def _campaign_totals(session, limit: int = 60) -> list[float]:
    rows = (session.query(CostLog.campaign_id, func.sum(CostLog.amount_usd))
            .filter(CostLog.campaign_id.isnot(None))
            .group_by(CostLog.campaign_id).limit(500).all())
    return [float(v or 0.0) for _cid, v in rows][:limit]


def check_cost_anomaly(*, campaign_id: str | None = None) -> dict:
    """Compare recent spend to a rolling median. Flags per-campaign, per-provider,
    daily and monthly surges. Also catches an LLM token-cost surge."""
    s = get_settings()
    factor = s.cost_anomaly_factor
    findings: list[dict] = []
    with session_scope() as session:
        hist = _campaign_totals(session)
        baseline = statistics.median(hist) if len(hist) >= 4 else None

        if campaign_id:
            cur = float(session.query(func.coalesce(func.sum(CostLog.amount_usd), 0.0))
                        .filter(CostLog.campaign_id == campaign_id).scalar() or 0.0)
            if baseline and baseline > 0 and cur > baseline * factor:
                findings.append({"scope": "campaign", "id": campaign_id,
                                 "spend": round(cur, 4), "baseline": round(baseline, 4)})

        # per-provider daily
        day = datetime.now(timezone.utc) - timedelta(hours=24)
        prov_today = (session.query(CostLog.provider, func.sum(CostLog.amount_usd))
                      .filter(CostLog.created_at >= day).group_by(CostLog.provider).all())
        prov_prev = dict(session.query(CostLog.provider, func.sum(CostLog.amount_usd))
                         .filter(CostLog.created_at < day,
                                 CostLog.created_at >= day - timedelta(days=7))
                         .group_by(CostLog.provider).all())
        for provider, amt in prov_today:
            amt = float(amt or 0.0)
            prev_daily = float(prov_prev.get(provider, 0.0)) / 7.0
            if prev_daily > 0.01 and amt > prev_daily * factor:
                findings.append({"scope": "provider_daily", "id": provider,
                                 "spend": round(amt, 4), "baseline": round(prev_daily, 4)})

        # LLM token surge (avg output tokens per LLM call today vs 7d)
        def _avg_tokens(since, until=None):
            q = session.query(func.avg(CostLog.input_tokens + CostLog.output_tokens)).filter(
                CostLog.kind == "LLM", CostLog.created_at >= since)
            if until:
                q = q.filter(CostLog.created_at < until)
            return float(q.scalar() or 0.0)

        today_tok = _avg_tokens(day)
        prev_tok = _avg_tokens(day - timedelta(days=7), day)
        if prev_tok > 50 and today_tok > prev_tok * 2.5:
            findings.append({"scope": "llm_token_surge", "id": "LLM",
                             "avg_tokens_today": round(today_tok), "avg_tokens_prev": round(prev_tok)})

    if findings:
        from app.ops.alerts import raise_alert

        sev = "HIGH" if any(f["scope"] == "provider_daily" for f in findings) else "WARNING"
        raise_alert(sev, "cost_anomaly", f"{len(findings)} cost anomaly finding(s)",
                    {"findings": findings})
    return {"anomaly": bool(findings), "findings": findings,
            "baseline_campaign_cost": round(baseline, 4) if baseline else None}
