"""ModelRouter — choose the engine for one task.

Inputs: agent_type, task_type, complexity, quality_required, budget_state,
privacy, latency_need, context_size, vision_required, + live model health.
Output: selected_model + ordered fallback_chain + human reason + estimated_cost.

Selection weighs task fit + quality + cost + latency + reliability + privacy —
**never price alone**. Deterministic tasks never touch a model. LOCAL_ONLY
(`allow_cloud_fallback=false`) removes every cloud model from consideration.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.ai_router.pricing import cost_of
from app.ai_router.registry import ModelEntry, get_registry
from app.config import get_settings

# task_type -> tier (spec §19)
DETERMINISTIC_TASKS = {
    "hash", "dedup", "similarity", "sort", "numeric", "validation", "cost_calc",
    "fingerprint", "regex_extract",
}
LOCAL_LIGHT_TASKS = {
    "classification", "tagging", "basic_extraction", "url_triage", "simple_summary",
    "dataset_cleanup", "topic_clustering", "language_detect", "keyword_extract",
}
STANDARD_TASKS = {
    "reference_analysis", "research_summary", "rewrite", "creative_qa_basic",
    "knowledge_extract", "fact_extract", "subtitle_polish", "platform_adapt",
}
PREMIUM_TASKS = {
    "strategy", "hook", "final_script", "creative_direction", "fact_conflict",
    "critical_reasoning", "prompt_distillation_final", "retention_direction",
}

# agent_type -> default tier when task_type is unknown (spec §22)
AGENT_TIER = {
    "Research Agent": "standard", "Fact Checker": "deterministic",
    "Data Curator": "local_light", "Dataset Analyzer": "local_light",
    "Strategist": "premium", "Hook Agent": "premium", "Script Agent": "premium",
    "Story Director": "premium", "Video Director": "premium",
    "Retention Director": "premium", "Subtitle Director": "local_light",
    "Voice Director": "standard", "Audio Director": "standard",
    "B-roll Director": "standard", "Graphics Director": "standard",
    "Thumbnail Director": "standard", "Platform Adapter": "standard",
    "Prompt Distillation": "local_light", "Governance": "deterministic",
}

_TIER_ORDER = ["deterministic", "local_light", "standard", "premium"]

_QUALITY_TO_MIN_TIER = {"fast": "local_light", "balanced": "local_light",
                        "high": "standard", "max": "standard"}


@dataclass
class RoutingDecision:
    task_type: str
    agent_type: str
    tier: str
    selected_model: str
    provider: str
    fallback_chain: list[str] = field(default_factory=list)
    reason: str = ""
    estimated_cost: dict | None = None
    deterministic: bool = False

    def as_dict(self) -> dict:
        return {**self.__dict__}


class ModelRouter:
    def __init__(self, registry=None):
        self.reg = registry or get_registry()

    def _tier_for(self, agent_type: str, task_type: str, complexity: str,
                  quality_required: str) -> str:
        if task_type in DETERMINISTIC_TASKS:
            return "deterministic"
        if task_type in LOCAL_LIGHT_TASKS:
            base = "local_light"
        elif task_type in STANDARD_TASKS:
            base = "standard"
        elif task_type in PREMIUM_TASKS:
            base = "premium"
        else:
            base = AGENT_TIER.get(agent_type, "standard")
        # complexity + explicit quality can bump one step up (never down past a floor)
        idx = _TIER_ORDER.index(base)
        if complexity == "high" and idx < len(_TIER_ORDER) - 1 and base != "deterministic":
            idx += 1
        if quality_required == "max" and base in ("local_light",):
            idx = max(idx, _TIER_ORDER.index("standard"))
        if quality_required == "fast" and base == "premium":
            idx = _TIER_ORDER.index("standard")   # 'fast' preset softens premium to standard
        return _TIER_ORDER[idx]

    def _candidates(self, tier: str, *, vision: bool, context_size: int,
                    privacy: str) -> list[ModelEntry]:
        s = get_settings()
        local = self.reg.usable(kind="local", vision=vision or None, min_context=context_size)
        cloud = [] if s.local_only or privacy == "local_only" else \
            self.reg.usable(kind="cloud", vision=vision or None, min_context=context_size)
        cloud_std = [e for e in cloud if e.quality_class in ("standard",)]
        cloud_prem = [e for e in cloud if e.quality_class == "premium"]
        # MOCK MODE stand-in — last-resort candidate so dev/test still gets a
        # routed decision + telemetry without a real key (executor swaps to MockLLM).
        mock = [] if (s.local_only or privacy == "local_only") else \
            self.reg.usable(kind="mock", min_context=context_size)
        # Honour the explicitly configured primary provider. A stale or invalid
        # cloud key must not take premium tasks away from a healthy local model.
        if s.llm_provider == "ollama":
            return local + cloud_prem + cloud_std + mock
        if tier == "local_light":
            return local + cloud_std + cloud_prem + mock
        if tier == "standard":
            return local + cloud_std + cloud_prem + mock
        if tier == "premium":
            return cloud_prem + cloud_std + local + mock
        return local + cloud_std + mock

    def _apply_performance(self, db, task_type: str, cands: list[ModelEntry]) -> list[ModelEntry]:
        """AUDIT-P8-005 — once telemetry has >= model_routing_min_sample obs for a
        (model, task), prefer a proven-STRONG engine and push a proven-WEAK one
        down. Unmeasured engines keep a neutral rank. No effect below the floor
        (performance_hint already drops UNKNOWN rows)."""
        try:
            from app.ai_router.telemetry import performance_hint

            hint = performance_hint(db, task_type=task_type)
        except Exception:  # noqa: BLE001 — auto-tune is advisory
            return cands
        if not hint:
            return cands
        rank = {"STRONG": 0, "OK": 1, "WEAK": 3}
        return sorted(cands, key=lambda e: rank.get(hint.get(e.model_id, ""), 2))

    def select(self, *, agent_type: str, task_type: str, complexity: str = "normal",
               quality_required: str | None = None, budget_state: str = "ok",
               privacy: str = "normal", latency_need: str = "normal",
               context_size: int = 2000, vision_required: bool = False,
               est_output_tokens: int = 400, db=None) -> RoutingDecision:
        s = get_settings()
        quality_required = quality_required or s.quality_preset
        tier = self._tier_for(agent_type, task_type, complexity, quality_required)

        if tier == "deterministic":
            return RoutingDecision(
                task_type=task_type, agent_type=agent_type, tier=tier,
                selected_model="python", provider="python", fallback_chain=[],
                reason="deterministic task — no model call", deterministic=True,
                estimated_cost={"usd": 0.0, "state": "KNOWN", "model": "python", "local": True})

        cands = self._candidates(tier, vision=vision_required, context_size=context_size,
                                 privacy=privacy)
        # budget pressure: prefer local, drop premium unless the tier demands it
        if budget_state in ("tight", "critical") and tier != "premium":
            cands = sorted(cands, key=lambda e: (e.kind != "local", e.quality_class))
        # latency pressure: down-rank slow models
        if latency_need == "low":
            cands = sorted(cands, key=lambda e: {"instant": 0, "fast": 1, "medium": 2, "slow": 3}
                           .get(e.latency_class, 2))
        # learned performance: prefer engines that actually do well on this task
        if db is not None and get_settings().model_routing_autotune_enabled:
            cands = self._apply_performance(db, task_type, cands)

        if not cands:
            # nothing available (e.g. LOCAL_ONLY + Ollama down) — honest failure signal
            return RoutingDecision(
                task_type=task_type, agent_type=agent_type, tier=tier,
                selected_model="", provider="", fallback_chain=[],
                reason=("no model available: "
                        + ("LOCAL_ONLY and local model is DOWN" if s.local_only
                           else "no local model and no cloud key")),
                estimated_cost={"usd": None, "state": "UNKNOWN"})

        chosen = cands[0]
        chain = [e.model_id for e in cands[1:4]]
        est = cost_of(chosen.model_id, input_tokens=context_size, output_tokens=est_output_tokens)
        reason = (f"tier={tier}; picked {chosen.model_id} ({chosen.kind}/{chosen.quality_class}, "
                  f"health={chosen.health}); fallback={chain or 'none'}")
        return RoutingDecision(
            task_type=task_type, agent_type=agent_type, tier=tier,
            selected_model=chosen.model_id, provider=chosen.provider,
            fallback_chain=chain, reason=reason, estimated_cost=est)


def route(**kw) -> RoutingDecision:
    return ModelRouter().select(**kw)
