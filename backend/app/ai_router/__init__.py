"""Model Registry + Model Router + Cost Estimator (Phase 8).

AI decides / code executes: the router picks *which* engine runs a task
(deterministic Python, local Ollama, cheap cloud, premium cloud) from task fit +
quality + cost + latency + reliability + privacy — never price alone. Local
failure never crashes the app; LOCAL_ONLY never calls a cloud model.
"""
from app.ai_router.registry import ModelRegistry, get_registry
from app.ai_router.router import ModelRouter, RoutingDecision, route
from app.ai_router.execute import run_routed
from app.ai_router.cost import estimate_campaign_cost

__all__ = [
    "ModelRegistry", "get_registry", "ModelRouter", "RoutingDecision", "route",
    "run_routed", "estimate_campaign_cost",
]
