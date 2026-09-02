from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from app.config import get_settings

CLOSED, OPEN, HALF_OPEN = "CLOSED", "OPEN", "HALF_OPEN"


class CircuitOpen(RuntimeError):
    def __init__(self, name: str, retry_after: float):
        super().__init__(f"circuit '{name}' is OPEN")
        self.name = name
        self.retry_after = retry_after


@dataclass
class _Breaker:
    name: str
    failure_threshold: int
    cooldown_s: float
    probes: int
    state: str = CLOSED
    failures: int = 0
    opened_at: float = 0.0
    half_open_calls: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def _now(self) -> float:
        return time.monotonic()

    def allow(self) -> bool:
        with self.lock:
            if self.state == CLOSED:
                return True
            if self.state == OPEN:
                if self._now() - self.opened_at >= self.cooldown_s:
                    self.state = HALF_OPEN
                    self.half_open_calls = 0
                    return True
                return False
            # HALF_OPEN
            if self.half_open_calls < self.probes:
                self.half_open_calls += 1
                return True
            return False

    def record_success(self) -> None:
        with self.lock:
            self.failures = 0
            if self.state in (HALF_OPEN, OPEN):
                self.state = CLOSED

    def record_failure(self) -> None:
        with self.lock:
            self.failures += 1
            if self.state == HALF_OPEN or self.failures >= self.failure_threshold:
                self.state = OPEN
                self.opened_at = self._now()

    def snapshot(self) -> dict:
        return {"state": self.state, "failures": self.failures,
                "retry_after": max(0.0, round(self.cooldown_s - (self._now() - self.opened_at), 1))
                if self.state == OPEN else 0.0}


_breakers: dict[str, _Breaker] = {}
_bl = threading.Lock()


def get_breaker(name: str) -> _Breaker:
    with _bl:
        b = _breakers.get(name)
        if b is None:
            s = get_settings()
            b = _Breaker(name, s.provider_breaker_threshold, s.provider_breaker_cooldown_s,
                         s.provider_breaker_probes)
            _breakers[name] = b
        return b


def call_with_breaker(name: str, fn, *, on_open=None):
    """Run fn() guarded by a named breaker. Raises CircuitOpen when open (unless
    on_open fallback given). A secondary that also fails does NOT loop — the
    breaker opens on it too."""
    b = get_breaker(name)
    if not b.allow():
        snap = b.snapshot()
        if on_open is not None:
            return on_open()
        raise CircuitOpen(name, snap["retry_after"])
    try:
        result = fn()
    except Exception:
        b.record_failure()
        raise
    b.record_success()
    return result


def all_breaker_states() -> dict:
    with _bl:
        return {name: b.snapshot() for name, b in _breakers.items()}


def reset_for_tests() -> None:
    with _bl:
        _breakers.clear()
