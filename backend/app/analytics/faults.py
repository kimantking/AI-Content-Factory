from __future__ import annotations

from dataclasses import dataclass, field

from app.analytics.base import AnalyticsError, AnalyticsErrorType


@dataclass
class _Plan:
    target: str          # platform or "*"
    error_type: AnalyticsErrorType
    remaining: int
    metric: str | None = None


@dataclass
class _Registry:
    plans: list[_Plan] = field(default_factory=list)

    def arm(self, target: str, error_type: AnalyticsErrorType, times: int = 1,
            metric: str | None = None) -> None:
        self.plans.append(_Plan(target, error_type, times, metric))

    def clear(self) -> None:
        self.plans.clear()

    def maybe_raise(self, platform: str, *, metric: str | None = None) -> None:
        for p in self.plans:
            if p.remaining <= 0:
                continue
            if p.target not in (platform, "*"):
                continue
            if p.metric and metric and p.metric != metric:
                continue
            p.remaining -= 1
            raise AnalyticsError(p.error_type, f"injected analytics fault for {p.target}",
                                 metric=p.metric, retry_after=1.0)


analytics_faults = _Registry()
