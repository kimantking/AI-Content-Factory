from __future__ import annotations

import os
import shutil
import time

from app.config import get_settings

_deep_cache: dict = {"at": 0.0, "data": None}
_DEEP_TTL = 60.0


def check_database() -> dict:
    try:
        from sqlalchemy import text

        from app.db.base import engine

        t = time.perf_counter()
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"status": "OK", "latency_ms": round((time.perf_counter() - t) * 1000, 1)}
    except Exception as e:  # noqa: BLE001
        return {"status": "DOWN", "error": type(e).__name__}


def check_redis() -> dict:
    try:
        import redis

        s = get_settings()
        t = time.perf_counter()
        redis.Redis.from_url(s.redis_url, socket_connect_timeout=2).ping()
        return {"status": "OK", "latency_ms": round((time.perf_counter() - t) * 1000, 1)}
    except Exception as e:  # noqa: BLE001
        return {"status": "DOWN", "error": type(e).__name__}


def check_storage() -> dict:
    from app.providers.media import get_storage

    try:
        stg = get_storage()
        probe = os.path.join(str(stg.root), ".health")
        os.makedirs(str(stg.root), exist_ok=True)
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        usage = shutil.disk_usage(str(stg.root))
        pct = round(usage.used / usage.total * 100, 1)
        st = "OK"
        s = get_settings()
        if pct >= s.disk_critical_pct:
            st = "CRITICAL"
        elif pct >= s.disk_warn_pct:
            st = "WARNING"
        return {"status": st, "disk_used_pct": pct,
                "free_gb": round(usage.free / 1e9, 1)}
    except Exception as e:  # noqa: BLE001
        return {"status": "DOWN", "error": type(e).__name__}


def check_queue() -> dict:
    try:
        from app.ops.queue_backpressure import backpressure_state

        return backpressure_state()
    except Exception as e:  # noqa: BLE001
        return {"status": "UNKNOWN", "error": type(e).__name__}


def liveness() -> dict:
    return {"status": "alive", "version": get_settings().app_version}


def readiness() -> dict:
    """Ready to serve requests? DB + Redis + storage must be usable. An external
    paid-provider outage does NOT flip readiness."""
    db, rds, stg = check_database(), check_redis(), check_storage()
    from app.ops.runtime_flags import maintenance_mode_active

    ready = (db["status"] == "OK" and rds["status"] == "OK"
             and stg["status"] in ("OK", "WARNING") and not maintenance_mode_active())
    return {
        "ready": ready,
        "checks": {"database": db, "redis": rds, "storage": stg},
        "maintenance_mode": maintenance_mode_active(),
    }


def dependencies() -> dict:
    return {"database": check_database(), "redis": check_redis(),
            "storage": check_storage(), "queue": check_queue()}


def deep_health(force: bool = False) -> dict:
    """Admin-only: probe external providers. Cached to avoid burning paid API
    calls on every request."""
    now = time.time()
    if not force and _deep_cache["data"] and now - _deep_cache["at"] < _DEEP_TTL:
        return {**_deep_cache["data"], "cached": True}

    from app.analytics.registry import all_analytics_platforms
    from app.autopilot.health import provider_health
    from app.publishing.capabilities import load_capabilities

    data = {
        "core": provider_health(),
        "publishers": {p: c.publishing_status for p, c in load_capabilities().items()},
        "analytics_platforms": all_analytics_platforms(),
        "circuit_breakers": _breaker_states(),
    }
    _deep_cache.update({"at": now, "data": data})
    return {**data, "cached": False}


def _breaker_states() -> dict:
    try:
        from app.ops.circuit_breaker import all_breaker_states

        return all_breaker_states()
    except Exception:  # noqa: BLE001
        return {}
