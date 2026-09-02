"""Phase 8 — Local AI + Model Router + Cost + Benchmark API."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.ai_router.benchmark import run_benchmark
from app.ai_router.cost import estimate_campaign_cost
from app.ai_router.execute import run_routed
from app.ai_router.registry import get_registry, reset_registry_cache
from app.ai_router.router import ModelRouter
from app.ai_router.telemetry import performance_hint, recompute_performance
from app.config import get_settings
from app.db.base import get_db
from app.db.models_p8 import ModelPerformance, ModelRoutingEvent

router = APIRouter(prefix="/api", tags=["ai"])

_AGENT_CHAT = {
    "research": ("Research Agent", "reference_analysis", "리서치 전문가", "근거와 출처 중심으로 조사 방향과 팩트를 설명합니다."),
    "script": ("Script Agent", "final_script", "대본 전문가", "훅, 흐름, 말투와 대본 개선안을 구체적으로 제안합니다."),
    "video": ("Video Director", "creative_direction", "영상 전문가", "장면, 촬영, 편집, 자막과 시청 유지 전략을 설명합니다."),
    "publish": ("Platform Adapter", "platform_adapt", "게시 전문가", "플랫폼별 게시 방식, 제목, 설명과 업로드 전략을 설명합니다."),
}


@router.post("/agents/{agent_id}/chat")
def agent_chat(agent_id: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    if agent_id not in _AGENT_CHAT:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="unknown agent")
    message = str(payload.get("message") or "").strip()
    if not message:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="message is required")
    message = message[:4000]
    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    safe_history = [
        {"role": str(row.get("role", ""))[:16], "content": str(row.get("content", ""))[:2000]}
        for row in history[-10:] if isinstance(row, dict)
    ]
    agent_type, task_type, ko_role, specialty = _AGENT_CHAT[agent_id]
    system = (
        f"당신은 AI Content Factory의 {ko_role}입니다. {specialty} "
        "사용자에게 한국어로 친절하고 간결하게 답하세요. 모르는 사실을 꾸며내지 말고, "
        "실행 가능한 다음 행동을 우선 제안하세요. 반드시 JSON 객체 {\"reply\": \"답변\"} 형식으로만 응답하세요."
    )
    result = run_routed(
        db, agent_type=agent_type, task_type=task_type, provider_task="agent_chat",
        system=system, user=message,
        context={"message": message, "history": safe_history, "agent_role": ko_role, "max_tokens": 700},
        complexity="normal", latency_need="low")
    db.commit()
    reply = result.data.get("reply") or result.data.get("text") or result.text
    if not reply:
        reply = "현재 연결된 AI 모델이 없습니다. 설정에서 Ollama 또는 클라우드 AI를 연결한 뒤 다시 말씀해 주세요."
    return {"reply": str(reply), "agent_id": agent_id, "provider": result.provider,
            "model": result.model_id, "mock": result.provider == "mock", "error": result.error}


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
