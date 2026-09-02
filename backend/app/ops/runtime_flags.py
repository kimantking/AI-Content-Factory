from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

# DB-backed operational flags. These MUST survive a process restart —
# EMERGENCY_STOP is the canonical example (Phase 4 must not auto-clear).

FLAG_EMERGENCY_STOP = "EMERGENCY_STOP"
FLAG_SAFE_MODE = "SAFE_MODE"
FLAG_MAINTENANCE_MODE = "MAINTENANCE_MODE"
# Phase 10 production kill switches (DB-backed, survive restart).
FLAG_PUBLISH_PAUSE = "GLOBAL_PUBLISH_PAUSE"          # no remote SNS publish, any platform
FLAG_PAID_PROVIDER_PAUSE = "GLOBAL_PAID_PROVIDER_PAUSE"  # no paid/cloud provider calls; local Ollama still allowed
_KNOWN = {FLAG_EMERGENCY_STOP, FLAG_SAFE_MODE, FLAG_MAINTENANCE_MODE,
          FLAG_PUBLISH_PAUSE, FLAG_PAID_PROVIDER_PAUSE}

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 3.0


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def get_flag(key: str) -> dict:
    hit = _CACHE.get(key)
    if hit and _now() - hit[0] < _TTL:
        return hit[1]
    from app.db.base import session_scope
    from app.db.models import RuntimeSetting

    with session_scope() as s:
        row = s.get(RuntimeSetting, key)
        val = dict(row.value) if row else {}
    _CACHE[key] = (_now(), val)
    return val


def set_flag(key: str, value: dict, *, actor: str = "user") -> dict:
    from app.db.base import session_scope
    from app.db.models import AuditEntry, RuntimeSetting

    with session_scope() as s:
        row = s.get(RuntimeSetting, key)
        old = dict(row.value) if row else {}
        if row is None:
            row = RuntimeSetting(key=key)
            s.add(row)
        row.value = value
        row.updated_by = actor
        row.updated_at = datetime.now(timezone.utc)
        s.add(AuditEntry(action=f"flag:{key}", actor=actor,
                         detail={"old": old, "new": value}))
    _CACHE.pop(key, None)
    return value


def _enabled(key: str) -> bool:
    return bool(get_flag(key).get("enabled"))


def emergency_stop_active() -> bool:
    return _enabled(FLAG_EMERGENCY_STOP)


def safe_mode_active() -> bool:
    return _enabled(FLAG_SAFE_MODE)


def maintenance_mode_active() -> bool:
    return _enabled(FLAG_MAINTENANCE_MODE)


def publish_paused() -> bool:
    """GLOBAL_PUBLISH_PAUSE — no remote SNS publish on any platform."""
    return _enabled(FLAG_PUBLISH_PAUSE)


def paid_provider_paused() -> bool:
    """GLOBAL_PAID_PROVIDER_PAUSE — no paid/cloud provider calls. Local Ollama
    and deterministic work continue."""
    return _enabled(FLAG_PAID_PROVIDER_PAUSE)


def all_flags() -> dict:
    return {k: get_flag(k) for k in _KNOWN}
