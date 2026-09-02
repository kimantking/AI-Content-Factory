"""run_routed — execute one task through the Model Router.

Resolves the RoutingDecision to a concrete provider, calls it, validates the
output, escalates on schema-invalid / low-confidence, walks the fallback chain on
provider failure, and records a ModelRoutingEvent. Respects LOCAL_ONLY (never
calls a cloud model) and never lets a local failure crash the caller.
"""
from __future__ import annotations

import json
import time

from sqlalchemy.orm import Session

from app.ai_router.pricing import cost_of
from app.ai_router.router import ModelRouter, RoutingDecision
from app.ai_router.telemetry import record_event
from app.config import get_settings
from app.providers.base import LLMResponse
from app.providers.errors import ProviderError


class RoutedResult:
    __slots__ = ("text", "data", "model_id", "provider", "tier", "latency_ms",
                 "fallback_used", "escalated", "cost", "decision", "error",
                 "input_tokens", "output_tokens", "reason")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def _provider_for(model_id: str, provider: str):
    s = get_settings()
    if provider == "ollama":
        from app.providers.ollama_llm import OllamaLLMProvider

        model = model_id.split("@")[0]
        return OllamaLLMProvider(base_url=s.ollama_base_url, model=model,
                                 timeout_seconds=s.local_model_timeout_seconds)
    if provider == "mock":
        if not s.mock_mode:
            raise ProviderError("MOCK provider is disabled in real mode", error_type="AUTH_ERROR")
        from app.providers.mock_llm import MockLLMProvider

        return MockLLMProvider()
    if provider == "anthropic":
        if s.local_only:
            raise ProviderError("LOCAL_ONLY: cloud provider disabled", error_type="AUTH_ERROR")
        try:
            from app.ops.runtime_flags import paid_provider_paused

            if paid_provider_paused():
                raise ProviderError("GLOBAL_PAID_PROVIDER_PAUSE: paid provider disabled",
                                    error_type="AUTH_ERROR")
        except ImportError:
            pass
        if not s.anthropic_api_key:
            raise ProviderError("Anthropic API key is not configured", error_type="AUTH_ERROR")
        from app.providers.anthropic_llm import AnthropicLLMProvider

        return AnthropicLLMProvider(api_key=s.anthropic_api_key or "", model=model_id,
                                   workspace_id=getattr(s, "anthropic_workspace_id", ""))
    raise ProviderError(f"unsupported LLM provider: {provider}", error_type="AUTH_ERROR")


def _confidence_ok(data: dict) -> bool:
    c = data.get("confidence")
    return not (isinstance(c, (int, float)) and c < 0.35)


def run_routed(db: Session | None, *, agent_type: str, task_type: str, system: str, user: str,
               context: dict | None = None, complexity: str = "normal",
               quality_required: str | None = None, budget_state: str = "ok",
               privacy: str = "normal", latency_need: str = "normal",
               vision_required: bool = False, workspace_id: str | None = None,
               campaign_id: str | None = None, provider_task: str | None = None,
               prompt_lineage: dict | None = None,
               decision: RoutingDecision | None = None) -> RoutedResult:
    context = dict(context or {})
    lineage = prompt_lineage or None
    ctx_size = max(200, len(system or "") // 4 + len(user or "") // 4)
    d = decision or ModelRouter().select(
        agent_type=agent_type, task_type=task_type, complexity=complexity,
        quality_required=quality_required, budget_state=budget_state, privacy=privacy,
        latency_need=latency_need, context_size=ctx_size, vision_required=vision_required,
        est_output_tokens=int(context.get("max_tokens", 400)), db=db)

    if d.deterministic or not d.selected_model:
        res = RoutedResult(text="", data={}, model_id=d.selected_model or "python",
                           provider=d.provider or "python", tier=d.tier, latency_ms=0,
                           fallback_used=False, escalated=False,
                           cost={"usd": 0.0, "state": "KNOWN", "local": True}, decision=d,
                           error=None if d.selected_model or d.deterministic else d.reason)
        return res

    chain = [(d.selected_model, d.provider)] + [
        (m, _prov_of(m)) for m in d.fallback_chain]
    last_err = None
    escalated = False
    for i, (mid, prov) in enumerate(chain):
        try:
            provider = _provider_for(mid, prov)
        except ProviderError as e:
            last_err = e
            continue
        # honesty (D4): if a mock stands in for the selected engine, record + cost
        # it as mock — never as the cloud model that was merely *chosen*.
        if type(provider).__name__ == "MockLLMProvider":
            mid, prov = "mock", "mock"
        started = time.monotonic()
        try:
            resp: LLMResponse = provider.complete(system=system, user=user,
                                                  task=provider_task or task_type,
                                                  context=context)
            latency_ms = round((time.monotonic() - started) * 1000)
        except ProviderError as e:
            last_err = e
            _rec(db, d, mid, prov, round((time.monotonic() - started) * 1000), 0, 0,
                 schema_valid=False, success=False, fallback_used=i > 0, escalated=escalated,
                 error_type=getattr(e, "error_type", "PROVIDER_ERROR"), agent_type=agent_type,
                 task_type=task_type, workspace_id=workspace_id, campaign_id=campaign_id,
                 prompt_lineage=lineage)
            continue

        try:
            data = json.loads(resp.text)
            schema_valid = isinstance(data, dict)
        except ValueError:
            data, schema_valid = {}, False

        est = cost_of(mid.split("@")[0], input_tokens=resp.input_tokens,
                      output_tokens=resp.output_tokens)
        _rec(db, d, mid, prov, latency_ms, resp.input_tokens, resp.output_tokens,
             schema_valid=schema_valid, success=schema_valid, fallback_used=i > 0,
             escalated=escalated, agent_type=agent_type, task_type=task_type,
             actual_cost_usd=est.get("usd"), cost_state=est.get("state", "UNKNOWN"),
             workspace_id=workspace_id, campaign_id=campaign_id, reason=d.reason,
             prompt_lineage=lineage)

        if schema_valid and _confidence_ok(data):
            return RoutedResult(text=resp.text, data=data, model_id=mid, provider=prov,
                                tier=d.tier, latency_ms=latency_ms, fallback_used=i > 0,
                                escalated=escalated, cost=est, decision=d, error=None,
                                input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
                                reason=d.reason)
        # schema invalid or low confidence -> escalate to the next (better) engine
        escalated = True
        last_err = ProviderError(f"{mid}: schema_invalid={not schema_valid} or low confidence",
                                 error_type="INVALID_OUTPUT")

    return RoutedResult(text="", data={}, model_id=chain[-1][0] if chain else "",
                        provider=chain[-1][1] if chain else "", tier=d.tier, latency_ms=0,
                        fallback_used=len(chain) > 1, escalated=escalated,
                        cost={"usd": None, "state": "UNKNOWN"}, decision=d,
                        error=str(last_err) if last_err else "no engine produced valid output")


def _prov_of(model_id: str) -> str:
    if model_id.startswith(("gemma", "ollama")) or "@" in model_id:
        return "ollama"
    if model_id.startswith("claude"):
        return "anthropic"
    return "mock"


def _rec(db, d, mid, prov, latency_ms, itok, otok, **kw):
    if db is None:
        return
    try:
        record_event(db, tier=d.tier, model_id=mid, provider=prov, latency_ms=latency_ms,
                     input_tokens=itok, output_tokens=otok,
                     estimated_cost_usd=(d.estimated_cost or {}).get("usd"), **kw)
    except Exception:  # noqa: BLE001 — telemetry must never break a task
        pass
