"""Model Execution Gateway (AUDIT-P8-001 repair).

The single door every content-production agent goes through to reach an LLM.
Instead of `get_llm_provider().complete(...)`, agents call
`routed_complete(...)`, which:

  1. maps (agent_type, task) -> a router task_type + tier,
  2. asks `ai_router.ModelRouter` to select an engine (deterministic Python /
     local Ollama / cheap cloud / premium cloud) from task fit + quality + cost +
     privacy + budget + provider health,
  3. runs it via `ai_router.run_routed` (structured-output validation +
     bounded escalation on schema-invalid / low-confidence + fallback chain +
     routing telemetry + cost/usage),
  4. on any router failure, falls back to the legacy provider so the pipeline
     never breaks (this is the one EXPLICIT_EXCEPTION direct-provider call).

LOCAL_ONLY, the local-only-invariant and the cheap-first policy all come for free
from the router — this module adds no new policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai_router.execute import run_routed
from app.config import get_settings
from app.providers.base import LLMResponse
from app.providers.registry import get_llm_provider

# agent task name (as passed inside nodes.py / media_nodes.py) ->
#   (router agent_type, router task_type)
_TASK_MAP: dict[str, tuple[str, str]] = {
    "research": ("Research Agent", "research_summary"),
    "fact_check": ("Fact Checker", "fact_extract"),
    "strategy": ("Strategist", "strategy"),
    "hook": ("Hook Agent", "hook"),
    "script": ("Script Agent", "final_script"),
    "script_qa": ("Script Agent", "creative_qa_basic"),
    "natural_writing": ("Script Agent", "rewrite"),
    # media pipeline
    "platform_adapt": ("Platform Adapter", "platform_adapt"),
    "scene_plan": ("Scene Planner", "creative_qa_basic"),
    "edit_decision": ("Video Editor", "subtitle_polish"),
    # autopilot topic extraction — a light extraction task
    "topic_extract": ("Strategist", "basic_extraction"),
}


def resolve_task(agent_name: str, task: str) -> tuple[str, str]:
    if task in _TASK_MAP:
        return _TASK_MAP[task]
    # unknown task -> route by the agent's default tier, standard fit
    return (agent_name or "Research Agent", "reference_analysis")


@dataclass
class GatewayResponse:
    text: str
    input_tokens: int
    output_tokens: int
    provider: str
    model: str
    tier: str = ""
    routing_reason: str = ""
    fallback_used: bool = False
    escalated: bool = False
    routed: bool = True
    # AUDIT-P8-006 — which PromptComposer output shaped `system`
    prompt_lineage: dict = field(default_factory=dict)

    def as_llm_response(self) -> LLMResponse:
        return LLMResponse(text=self.text, input_tokens=self.input_tokens,
                           output_tokens=self.output_tokens, provider=self.provider,
                           model=self.model)


_EMPTY_LINEAGE = {
    "prompt_composer_used": False, "skill_ids": [], "blueprint_ids": [],
    "memory_ids": [], "prompt_version": "", "context_tokens": 0, "truncated": False,
}


def _facets(session: Session | None, campaign_id: str | None, workspace_id: str | None,
            context: dict) -> dict:
    """Derive (workspace_id, brand_id, platform, content_type, topic_cluster) for
    agent-specific + platform-specific learned-context retrieval."""
    f = {"workspace_id": workspace_id, "brand_id": None,
         "platform": context.get("platform"), "content_type": context.get("content_type"),
         "topic_cluster": context.get("topic_cluster")}
    if session is None or not campaign_id:
        return f
    try:
        from app.db.models import Campaign

        camp = session.get(Campaign, campaign_id)
        if camp is not None:
            f["workspace_id"] = workspace_id or camp.workspace_id
            f["brand_id"] = camp.brand_id
            if not f["platform"]:
                plats = list(camp.platforms or [])
                f["platform"] = plats[0] if plats else None
    except Exception:  # noqa: BLE001 — retrieval facets are best-effort
        pass
    return f


def _compose_system(system: str, *, agent_type: str, session: Session | None,
                    campaign_id: str | None, workspace_id: str | None,
                    context: dict, prompt_version: str) -> tuple[str, dict]:
    """Merge Base + Brand/Channel/Memory + relevant Learned Skills + Prompt
    Blueprints under the context budget (AUDIT-P8-006). Advisory, never a new
    LLM call: retrieval is deterministic DB reads (spec §15)."""
    s = get_settings()
    lineage = {**_EMPTY_LINEAGE, "prompt_version": prompt_version,
               "context_tokens": max(1, round(len(system or "") / 4))}
    if not s.prompt_composer_enabled or session is None:
        return system, lineage
    try:
        from app.intel.composer import compose

        fac = _facets(session, campaign_id, workspace_id, context)
        mem = context.get("_memory_context") or {}
        out = compose(
            session, agent_type=agent_type, base_prompt=system,
            workspace_id=fac["workspace_id"], brand_id=fac["brand_id"],
            memory_context=(mem.get("text") or "") if isinstance(mem, dict) else "",
            memory_ids=[m.get("id") for m in (mem.get("items") or [])
                        if isinstance(m, dict) and m.get("id")] if isinstance(mem, dict) else [],
            platform=fac["platform"], content_type=fac["content_type"],
            topic_cluster=fac["topic_cluster"],
        )
        lineage.update(
            prompt_composer_used=True, skill_ids=out["used_skills"],
            blueprint_ids=out["used_blueprints"], memory_ids=out.get("used_memory", []),
            context_tokens=lineage["context_tokens"] + int(out.get("learned_tokens", 0)),
            truncated=bool(out.get("truncated")),
        )
        return (out["prompt"] if out.get("changed") else system), lineage
    except Exception:  # noqa: BLE001 — composition is advisory; never break a run
        return system, lineage


def routed_complete(*, agent_name: str, task: str, system: str, user: str,
                    context: dict | None = None, session: Session | None = None,
                    campaign_id: str | None = None, workspace_id: str | None = None,
                    complexity: str = "normal", quality_required: str | None = None,
                    vision_required: bool = False) -> GatewayResponse:
    context = dict(context or {})
    agent_type, task_type = resolve_task(agent_name, task)

    # AUDIT-P8-006 — Base + Brand/Channel/Memory + Learned Skills + Prompt
    # Blueprints, under the context budget, BEFORE routing.
    system, lineage = _compose_system(
        system, agent_type=agent_type, session=session, campaign_id=campaign_id,
        workspace_id=workspace_id, context=context, prompt_version=str(task))

    try:
        r = run_routed(
            session, agent_type=agent_type, task_type=task_type, system=system,
            user=user, context=context, complexity=complexity,
            quality_required=quality_required, vision_required=vision_required,
            workspace_id=workspace_id, campaign_id=campaign_id,
            provider_task=task,   # provider/mock keys off the ORIGINAL task label
            prompt_lineage=lineage)
    except Exception as e:  # noqa: BLE001 — router must never break production
        return _legacy_fallback(system, user, task, context, reason=f"router error: {e}",
                                lineage=lineage)

    if r.error or not r.text:
        return _legacy_fallback(system, user, task, context,
                                reason=f"router: {r.error or 'no output'}", lineage=lineage)
    return GatewayResponse(
        text=r.text, input_tokens=int(r.input_tokens or _approx(system + user)),
        output_tokens=int(r.output_tokens or _approx(r.text)),
        provider=r.provider or "", model=(r.model_id or "").split("@")[0],
        tier=r.tier or "", routing_reason=r.reason or (r.decision.reason if r.decision else ""),
        fallback_used=bool(r.fallback_used), escalated=bool(r.escalated), routed=True,
        prompt_lineage=lineage)


def _legacy_fallback(system: str, user: str, task: str, context: dict,
                     *, reason: str, lineage: dict | None = None) -> GatewayResponse:
    """EXPLICIT_EXCEPTION: the only sanctioned direct provider call outside the
    router — a safety net so a router hiccup never fails a campaign."""
    prov = get_llm_provider()
    resp = prov.complete(system=system, user=user, task=task, context=context)
    return GatewayResponse(
        text=resp.text, input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
        provider=resp.provider, model=resp.model, tier="legacy_fallback",
        routing_reason=reason, routed=False, prompt_lineage=lineage or dict(_EMPTY_LINEAGE))


def _approx(text: str) -> int:
    return max(1, round(len(text or "") / 4))


class GatewayLLM:
    """Thin `.complete`-shaped shim so callers that expect an `LLMProvider`
    (e.g. `naturalness.natural_writing_pass(llm=...)`) route through the gateway."""

    name = "gateway"
    model = "routed"

    def __init__(self, *, agent_name: str, session: Session | None = None,
                 campaign_id: str | None = None, workspace_id: str | None = None):
        self._agent = agent_name
        self._session = session
        self._cid = campaign_id
        self._wid = workspace_id

    def complete(self, *, system: str, user: str, task: str, context: dict) -> LLMResponse:
        return routed_complete(
            agent_name=self._agent, task=task, system=system, user=user, context=context,
            session=self._session, campaign_id=self._cid, workspace_id=self._wid,
        ).as_llm_response()
