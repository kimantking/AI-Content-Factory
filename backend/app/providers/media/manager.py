from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from app.providers.errors import NON_RETRYABLE, ProviderError
from app.schemas.media import ProviderMode


@dataclass
class ProviderRecord:
    name: str
    provider: object
    priority: int = 100
    enabled: bool = True
    timeout: float = 60.0
    max_retry: int = 2
    estimated_cost: float = 0.0
    health_status: str = "OK"          # OK | DEGRADED | DOWN
    mode: ProviderMode = ProviderMode.MOCK


@dataclass
class ProviderManager:
    """Ordered pool for one media kind. Primary → retry → secondary → …
    Health is updated as calls succeed/fail so a flapping provider is de-prioritised."""

    kind: str
    records: list[ProviderRecord] = field(default_factory=list)

    def add(self, rec: ProviderRecord) -> "ProviderManager":
        self.records.append(rec)
        self.records.sort(key=lambda r: r.priority)
        return self

    def _ordered(self) -> list[ProviderRecord]:
        live = [r for r in self.records if r.enabled and r.health_status != "DOWN"]
        return live or [r for r in self.records if r.enabled]

    def call(self, op: Callable[[object], object], *, note: str = ""):
        errors: list[str] = []
        for rec in self._ordered():
            for attempt in range(1, rec.max_retry + 1):
                try:
                    result = op(rec.provider)
                    rec.health_status = "OK"
                    return result, rec
                except ProviderError as e:
                    etype = getattr(e, "error_type", "PROVIDER_ERROR")
                    errors.append(f"{rec.name}#{attempt}:{etype}")
                    if etype in NON_RETRYABLE:
                        rec.health_status = "DEGRADED"
                        raise
                    rec.health_status = "DEGRADED" if attempt < rec.max_retry else "DOWN"
                    time.sleep(0.02 * attempt)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{rec.name}#{attempt}:{type(e).__name__}")
                    rec.health_status = "DOWN"
                    break
        raise ProviderError(
            f"all {self.kind} providers failed ({note}): {', '.join(errors)}"
        )
