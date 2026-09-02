from __future__ import annotations

from app.config import get_settings

REQUIRED = ["llm", "search", "database", "redis", "storage"]
OPTIONAL = ["image", "video", "tts", "publishers"]


def provider_health() -> dict:
    """Best-effort health of everything an Autopilot run depends on. In mock mode
    the mock providers are always up; DB/Redis are probed for real."""
    s = get_settings()
    out: dict[str, str] = {}

    out["llm"] = "OK"        # mock or configured
    out["search"] = "OK" if s.search_is_mock or s.tavily_api_key else "DEGRADED"
    out["image"] = "OK"
    out["video"] = "FALLBACK"   # no real video provider -> image-motion fallback (Phase 1-B)
    out["tts"] = "OK"
    out["storage"] = "OK"

    try:
        from app.db.base import engine
        from sqlalchemy import text

        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        out["database"] = "OK"
    except Exception:  # noqa: BLE001
        out["database"] = "DOWN"

    try:
        import redis

        redis.Redis.from_url(s.redis_url, socket_connect_timeout=2).ping()
        out["redis"] = "OK"
    except Exception:  # noqa: BLE001
        out["redis"] = "DOWN"

    try:
        from app.db.base import session_scope
        from app.db.models import PlatformAccount

        with session_scope() as sess:
            n = sess.query(PlatformAccount).filter_by(connection_status="CONNECTED").count()
        out["publishers"] = "OK" if n else "NONE_CONNECTED"
    except Exception:  # noqa: BLE001
        out["publishers"] = "UNKNOWN"

    return out


def run_allowed(health: dict | None = None) -> tuple[bool, list[str]]:
    h = health or provider_health()
    down = [k for k in REQUIRED if h.get(k) in ("DOWN", "UNAVAILABLE")]
    return (not down), down
