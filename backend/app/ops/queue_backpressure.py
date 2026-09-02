from __future__ import annotations

from app.config import get_settings

_QUEUES = ("celery", "image", "video", "audio", "render", "publish", "analytics", "autopilot")


def queue_depths() -> dict[str, int]:
    try:
        import redis

        r = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        return {q: int(r.llen(q)) for q in _QUEUES}
    except Exception:  # noqa: BLE001
        return {q: 0 for q in _QUEUES}


def backpressure_state() -> dict:
    """NORMAL -> keep going; SLOW -> autopilot reduces production rate;
    HOLD -> no new production. Wired into the Phase 4 health gate / watchdog."""
    s = get_settings()
    depths = queue_depths()
    worst = max(depths.values()) if depths else 0
    if worst >= s.queue_backpressure_hold:
        status = "HOLD"
    elif worst >= s.queue_backpressure_warn:
        status = "SLOW"
    else:
        status = "NORMAL"
    return {"status": status, "worst_depth": worst, "depths": depths,
            "warn_at": s.queue_backpressure_warn, "hold_at": s.queue_backpressure_hold}


def production_allowed() -> tuple[bool, str]:
    st = backpressure_state()
    if st["status"] == "HOLD":
        return False, f"queue backpressure HOLD (depth {st['worst_depth']})"
    return True, st["status"]
