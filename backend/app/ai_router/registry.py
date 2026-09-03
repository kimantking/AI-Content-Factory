"""ModelRegistry — the set of engines the router can choose from, with capability
/ health / pricing metadata. Health for local models is probed live from Ollama;
cloud models are ENABLED only when a key is configured.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.ai_router.pricing import price_for
from app.config import get_settings

# quality/latency classes are ordinal: higher = better / slower
QUALITY = {"basic": 1, "standard": 2, "high": 3, "premium": 4}
LATENCY = {"instant": 1, "fast": 2, "medium": 3, "slow": 4}


@dataclass
class ModelEntry:
    model_id: str
    provider: str            # python | ollama | anthropic
    family: str
    kind: str                # deterministic | local | cloud
    enabled: bool = True
    health: str = "UNKNOWN"  # OK | DEGRADED | DOWN | UNKNOWN
    vision: bool = False
    tools: bool = False
    context_tokens: int = 8192
    latency_class: str = "medium"
    quality_class: str = "standard"
    pricing_state: str = "UNKNOWN"
    benchmark_state: str = "NONE"   # NONE | PARTIAL | BENCHMARKED

    def as_dict(self) -> dict:
        inp, out, pstate = price_for(self.model_id)
        return {**self.__dict__, "input_usd_per_1k": inp, "output_usd_per_1k": out,
                "pricing_state": pstate}


class ModelRegistry:
    def __init__(self, entries: list[ModelEntry]):
        self._by_id = {e.model_id: e for e in entries}

    def all(self) -> list[ModelEntry]:
        return list(self._by_id.values())

    def get(self, model_id: str) -> ModelEntry | None:
        return self._by_id.get(model_id)

    def usable(self, *, kind: str | None = None, vision: bool | None = None,
              min_context: int = 0) -> list[ModelEntry]:
        out = []
        for e in self._by_id.values():
            if not e.enabled or e.health == "DOWN":
                continue
            if kind and e.kind != kind:
                continue
            if vision and not e.vision:
                continue
            if min_context and e.context_tokens < min_context:
                continue
            out.append(e)
        return out

    def refresh_health(self) -> None:
        """Live-probe local models; mark cloud enabled/disabled by config."""
        s = get_settings()
        py = self._by_id.get("python")
        if py:
            py.health = "OK"
        # local
        local_ids = [mid for mid, e in self._by_id.items() if e.kind == "local"]
        if local_ids:
            status = "DOWN"
            models: list[str] = []
            if s.ollama_enabled:
                try:
                    from app.providers.ollama_llm import OllamaLLMProvider

                    h = OllamaLLMProvider(base_url=s.ollama_base_url,
                                          model=s.ollama_default_model).health()
                    status = {"CONNECTED": "OK", "DEGRADED": "DEGRADED"}.get(h["status"], "DOWN")
                    models = h.get("models", [])
                except Exception:  # noqa: BLE001 — never crash on a health probe
                    status = "DOWN"
            for mid in local_ids:
                e = self._by_id[mid]
                e.enabled = bool(s.ollama_enabled)
                e.health = status if (mid in models or status == "DOWN") else "DEGRADED"
        # cloud
        for e in self._by_id.values():
            if e.kind != "cloud":
                continue
            e.enabled = bool(s.anthropic_api_key) and not s.local_only
            e.health = "OK" if e.enabled else "DOWN"
        # mock — the executor's stand-in when MOCK MODE is on (D4). Keeps the
        # router producing a real decision + telemetry in dev/test without a key.
        m = self._by_id.get("mock")
        if m is not None:
            m.enabled = bool(s.llm_is_mock)
            m.health = "OK" if m.enabled else "DOWN"


def _default_entries() -> list[ModelEntry]:
    s = get_settings()
    return [
        ModelEntry("python", "python", "deterministic", "deterministic", enabled=True,
                   health="OK", context_tokens=0, latency_class="instant",
                   quality_class="basic", pricing_state="KNOWN", benchmark_state="BENCHMARKED"),
        ModelEntry(s.ollama_default_model, "ollama", "gemma3", "local",
                   enabled=s.ollama_enabled, context_tokens=8192, latency_class="medium",
                   quality_class="standard", tools=False, vision=False,
                   pricing_state="KNOWN"),
        ModelEntry("claude-haiku-4-5-20251001", "anthropic", "claude", "cloud",
                   enabled=bool(s.anthropic_api_key) and not s.local_only,
                   context_tokens=200_000, latency_class="fast", quality_class="standard",
                   tools=True, vision=True, pricing_state="ESTIMATED"),
        ModelEntry(s.anthropic_model or "claude-sonnet-5", "anthropic", "claude", "cloud",
                   enabled=bool(s.anthropic_api_key) and not s.local_only,
                   context_tokens=200_000, latency_class="medium", quality_class="premium",
                   tools=True, vision=True, pricing_state="ESTIMATED"),
        ModelEntry("mock", "mock", "mock", "mock", enabled=bool(s.llm_is_mock),
                   health="OK", context_tokens=200_000, latency_class="instant",
                   quality_class="standard", tools=True, vision=True, pricing_state="KNOWN",
                   benchmark_state="BENCHMARKED"),
    ]


@lru_cache(maxsize=1)
def _cached_registry() -> ModelRegistry:
    return ModelRegistry(_default_entries())


def get_registry(*, refresh: bool = True) -> ModelRegistry:
    reg = _cached_registry()
    if refresh:
        reg.refresh_health()
    return reg


def reset_registry_cache() -> None:
    _cached_registry.cache_clear()
