from __future__ import annotations

import threading
import time

from app.config import get_settings

# In-process token bucket. For a single-node deployment this is enough; a
# multi-node deployment would back this with Redis (same interface).

# route class -> (capacity, refill per second)
_LIMITS: dict[str, tuple[float, float]] = {
    "default": (120, 2.0),
    "auth": (10, 0.2),
    "campaign_create": (12, 0.05),
    "media": (20, 0.05),
    "publish": (30, 0.1),
    "analytics": (60, 1.0),
    "autopilot": (10, 0.02),
    "webhook": (240, 8.0),
    "metrics": (60, 1.0),
}

_buckets: dict[tuple[str, str], list[float]] = {}
_lock = threading.Lock()


class RateLimited(Exception):
    def __init__(self, retry_after: float):
        super().__init__("rate limit exceeded")
        self.retry_after = retry_after


def _now() -> float:
    return time.monotonic()


def check(route_class: str, client: str) -> None:
    if not get_settings().rate_limit_enabled:
        return
    cap, refill = _LIMITS.get(route_class, _LIMITS["default"])
    key = (route_class, client)
    with _lock:
        state = _buckets.get(key)
        now = _now()
        if state is None:
            state = [cap, now]
        tokens, last = state
        tokens = min(cap, tokens + (now - last) * refill)
        if tokens < 1.0:
            _buckets[key] = [tokens, now]
            raise RateLimited(round((1.0 - tokens) / refill, 2))
        _buckets[key] = [tokens - 1.0, now]


def classify_path(path: str, method: str) -> str:
    if path.startswith("/webhooks/"):
        return "webhook"
    if path == "/metrics":
        return "metrics"
    if "/publishing/" in path and method == "POST":
        return "publish"
    if "/autopilot/" in path and method == "POST":
        return "autopilot"
    if path.endswith("/campaigns") and method == "POST":
        return "campaign_create"
    if "/media" in path and method == "POST":
        return "media"
    if "/analytics" in path or "/learning" in path:
        return "analytics"
    if "oauth" in path or "connect" in path:
        return "auth"
    return "default"


def reset_for_tests() -> None:
    with _lock:
        _buckets.clear()
