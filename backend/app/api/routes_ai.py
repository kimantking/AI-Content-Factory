"""Phase 8 — Local AI + Model Router + Cost + Benchmark API."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.ai_router.benchmark import run_benchmark
from app.ai_router.cost import estimate_campaign_cost
from app.ai_router.registry import get_registry, reset_registry_cache
from app.ai_router.router import ModelRouter
from app.ai_router.telemetry import performance_hint, recompute_performance
from app.config import get_settings
from app.db.base import get_db
from app.db.models_p8 import ModelPerformance, ModelRoutingEvent

router = APIRouter(prefix="/api", tags=["ai"])


@router.get("/local-ai/status")
def local_ai_status():
    s = get_settings()
    out = {"ollama_enabled": s.ollama_enabled, "base_url": s.ollama_base_url,
           "default_model": s.ollama_default_model, "allow_cloud_fallback": s.allow_cloud_fallback,
           "local_only": s.local_only, "status": "DISABLED", "models": [], "version": None}
    if not s.ollama_enabled:
        return out
    try:
        from app.providers.ollama_llm import OllamaLLMProvider

        h = OllamaLLMProvider(base_url=s.ollama_base_url, model=s.ollama_default_model).health()
        out.update({"status": {"CONNECTED": "CONNECTED", "DEGRADED": "DEGRADED"}.get(
            h["status"], "NOT_RUNNING"), "models": h["models"], "version": h.get("version"),
            "reason": h.get("reason", "")})
        if h["status"] == "CONNECTED" and s.ollama_default_model not in h["models"]:
            out["status"] = "NO_MODEL"
    except Exception as e:  # noqa: BLE001
        out["status"] = "NOT_RUNNING"
        out["reason"] = str(e)
    return out


@router.post("/local-ai/ping")
def local_ai_ping():
    s = get_settings()
    if not s.ollama_enabled:
        return {"ok": False, "error": "OLLAMA_ENABLED is false"}
    from app.providers.ollama_llm import OllamaLLMProvider

    return OllamaLLMProvider(base_url=s.ollama_base_url, model=s.ollama_default_model).ping_inference()


@router.get("/models")
def list_models(refresh: bool = True):
    reset_registry_cache()
    reg = get_registry(refresh=refresh)
    return [e.as_dict() for e in reg.all()]


@router.post("/models/route")
def preview_route(payload: dict = Body(...)):
    d = ModelRouter().select(
        agent_type=payload.get("agent_type", "Research Agent"),
        task_type=payload.get("task_type", "reference_analysis"),
        complexity=payload.get("complexity", "normal"),
        quality_required=payload.get("quality_required"),
        budget_state=payload.get("budget_state", "ok"),
        privacy=payload.get("privacy", "normal"),
        latency_need=payload.get("latency_need", "normal"),
        context_size=int(payload.get("context_size", 2000)),
        vision_required=bool(payload.get("vision_required", False)))
    return d.as_dict()


@router.post("/models/benchmark")
def benchmark(payload: dict = Body(default={}), db: Session = Depends(get_db)):
    s = get_settings()
    model_id = payload.get("model_id") or s.ollama_default_model
    provider = payload.get("provider")
    res = run_benchmark(db, model_id=model_id, provider=provider)
    db.commit()
    return res


@router.get("/models/performance")
def model_performance(task_type: str | None = None, db: Session = Depends(get_db)):
    q = db.query(ModelPerformance)
    if task_type:
        q = q.filter(ModelPerformance.task_type == task_type)
    return [{"model_id": r.model_id, "task_type": r.task_type, "sample_size": r.sample_size,
             "schema_valid_rate": r.schema_valid_rate, "success_rate": r.success_rate,
             "avg_latency_ms": r.avg_latency_ms, "avg_quality": r.avg_quality,
             "avg_cost_usd": r.avg_cost_usd, "strength": r.strength,
             "benchmark_state": r.benchmark_state}
            for r in q.order_by(ModelPerformance.task_type).all()]


@router.post("/models/performance/recompute")
def recompute(db: Session = Depends(get_db)):
    n = recompute_performance(db)
    db.commit()
    return {"rows": n}


@router.get("/routing/telemetry")
def routing_telemetry(limit: int = 100, campaign_id: str | None = None,
                      db: Session = Depends(get_db)):
    q = db.query(ModelRoutingEvent)
    if campaign_id:
        q = q.filter(ModelRoutingEvent.campaign_id == campaign_id)
    return [{"agent_type": e.agent_type, "task_type": e.task_type, "tier": e.tier,
             "model_id": e.model_id, "provider": e.provider, "latency_ms": e.latency_ms,
             "estimated_cost_usd": e.estimated_cost_usd, "actual_cost_usd": e.actual_cost_usd,
             "cost_state": e.cost_state, "schema_valid": e.schema_valid, "success": e.success,
             "fallback_used": e.fallback_used, "escalated": e.escalated,
             "created_at": e.created_at.isoformat() if e.created_at else None}
            for e in q.order_by(ModelRoutingEvent.created_at.desc()).limit(min(limit, 500)).all()]


@router.post("/cost/estimate")
def cost_estimate(payload: dict = Body(...), db: Session = Depends(get_db)):
    return estimate_campaign_cost(
        db, selection=payload.get("selection", {}),
        quality_preset=payload.get("quality_preset"),
        execution_mode=payload.get("execution_mode", "CREATE_AND_LEARN"),
        reference_count=int(payload.get("reference_count", 0)),
        privacy=payload.get("privacy", "normal"),
        budget_state=payload.get("budget_state", "ok"))
