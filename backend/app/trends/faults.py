from __future__ import annotations

from dataclasses import dataclass, field

from app.trends.base import TrendError


@dataclass
class _Plan:
    target: str
    error_type: str
    remaining: int


@dataclass
class _Reg:
    plans: list[_Plan] = field(default_factory=list)

    def arm(self, target: str, error_type: str = "PROVIDER_ERROR", times: int = 1) -> None:
        self.plans.append(_Plan(target, error_type, times))

    def clear(self) -> None:
        self.plans.clear()

    def maybe_raise(self, source_id: str) -> None:
        for p in self.plans:
            if p.remaining > 0 and p.target in (source_id, "*"):
                p.remaining -= 1
                raise TrendError(f"injected trend fault for {p.target}", error_type=p.error_type)


trend_faults = _Reg()
