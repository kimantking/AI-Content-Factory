from __future__ import annotations

from dataclasses import dataclass, field

from app.providers.errors import ProviderError


@dataclass
class _FaultPlan:
    target: str          # e.g. "search", "llm:research"
    error_type: str
    remaining: int


@dataclass
class _FaultRegistry:
    plans: list[_FaultPlan] = field(default_factory=list)

    def arm(self, target: str, error_type: str = "PROVIDER_ERROR", times: int = 1) -> None:
        self.plans.append(_FaultPlan(target=target, error_type=error_type, remaining=times))

    def clear(self) -> None:
        self.plans.clear()

    def maybe_raise(self, *targets: str) -> None:
        for plan in self.plans:
            if plan.remaining > 0 and plan.target in targets:
                plan.remaining -= 1
                raise ProviderError(
                    f"injected fault for {plan.target}", error_type=plan.error_type
                )


faults = _FaultRegistry()
