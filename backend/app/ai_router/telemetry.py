"""Routing telemetry + model performance memory.

record_event() writes one ModelRoutingEvent per routed call. recompute_performance()
rolls those into per-(model, task) ModelPerformance rows. The router reads
performance back to prefer engines that actually do well on a task — but only once
`model_routing_min_sample` observations exist (no policy flip on n=1).
"""
from __future__ import annotations

from sqlalchemy import Integer, cast
from sqlalchemy import func as safunc
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models_p8 import ModelPerformance, ModelRoutingEvent


def record_event(db: Session, *, agent_type: str, task_type: str, tier: str, model_id: str,
                 provider: str, latency_ms: int, input_tokens: int = 0, output_tokens: int = 0,
                 estimated_cost_usd: float | None = None, actual_cost_usd: float | None = None,
                 cost_state: str = "UNKNOWN", schema_valid: bool = True,
                 quality_signal: float | None = None, success: bool = True,
                 fallback_used: bool = False, escalated: bool = False, error_type: str = "",
                 reason: str = "", workspace_id: str | None = None,
                 campaign_id: str | None = None,
                 prompt_lineage: dict | None = None) -> ModelRoutingEvent:
    ev = ModelRoutingEvent(
        workspace_id=workspace_id, campaign_id=campaign_id, agent_type=agent_type,
        task_type=task_type, tier=tier, model_id=model_id, provider=provider,
        latency_ms=int(latency_ms), input_tokens=int(input_tokens), output_tokens=int(output_tokens),
        estimated_cost_usd=estimated_cost_usd, actual_cost_usd=actual_cost_usd,
        cost_state=cost_state, schema_valid=schema_valid, quality_signal=quality_signal,
        success=success, fallback_used=fallback_used, escalated=escalated,
        error_type=error_type, reason=reason[:2000], prompt_lineage=prompt_lineage or None)
    db.add(ev)
    db.flush()
    return ev


def recompute_performance(db: Session, *, model_id: str | None = None,
                          task_type: str | None = None) -> int:
    q = db.query(
        ModelRoutingEvent.model_id, ModelRoutingEvent.task_type,
        safunc.count(ModelRoutingEvent.id),
        safunc.avg(cast(ModelRoutingEvent.schema_valid, Integer)),
        safunc.avg(cast(ModelRoutingEvent.success, Integer)),
        safunc.avg(ModelRoutingEvent.latency_ms),
        safunc.avg(ModelRoutingEvent.quality_signal),
        safunc.avg(ModelRoutingEvent.actual_cost_usd),
    ).filter(ModelRoutingEvent.model_id != "")
    if model_id:
        q = q.filter(ModelRoutingEvent.model_id == model_id)
    if task_type:
        q = q.filter(ModelRoutingEvent.task_type == task_type)
    q = q.group_by(ModelRoutingEvent.model_id, ModelRoutingEvent.task_type)

    n = 0
    for mid, tt, cnt, sv, sr, lat, ql, cost in q.all():
        row = (db.query(ModelPerformance)
               .filter_by(model_id=mid, task_type=tt).first())
        if row is None:
            row = ModelPerformance(model_id=mid, task_type=tt)
            db.add(row)
        row.sample_size = int(cnt or 0)
        row.schema_valid_rate = round(float(sv or 0), 3)
        row.success_rate = round(float(sr or 0), 3)
        row.avg_latency_ms = round(float(lat or 0), 1)
        row.avg_quality = round(float(ql), 3) if ql is not None else None
        row.avg_cost_usd = round(float(cost), 6) if cost is not None else None
        row.strength = _strength(row)
        n += 1
    db.flush()
    return n


def _strength(row: ModelPerformance) -> str:
    if row.sample_size < get_settings().model_routing_min_sample:
        return "UNKNOWN"
    score = 0.5 * row.schema_valid_rate + 0.5 * row.success_rate
    if row.avg_quality is not None:
        score = 0.4 * row.schema_valid_rate + 0.3 * row.success_rate + 0.3 * row.avg_quality
    return "STRONG" if score >= 0.85 else "OK" if score >= 0.6 else "WEAK"


def performance_hint(db: Session, *, task_type: str) -> dict[str, str]:
    """{model_id: strength} for a task, only for rows with enough samples."""
    rows = db.query(ModelPerformance).filter_by(task_type=task_type).all()
    return {r.model_id: r.strength for r in rows if r.strength != "UNKNOWN"}
