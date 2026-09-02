from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.publishing.base import RECOVERY, TERMINAL_RECOVERY, PublishErrorType

_BASE_DELAY = 30.0     # seconds
_FACTOR = 2.0
_MAX_DELAY = 3600.0


def backoff_seconds(attempt: int, retry_after: float | None = None) -> float:
    if retry_after:
        return min(_MAX_DELAY, max(retry_after, 1.0))
    return min(_MAX_DELAY, _BASE_DELAY * (_FACTOR ** max(0, attempt - 1)))


def plan(error_type: PublishErrorType, *, attempt: int, max_attempts: int,
         retry_after: float | None = None) -> dict:
    """Decide what to do after a publish error."""
    action = RECOVERY.get(error_type, "RETRY")
    if action in TERMINAL_RECOVERY:
        return {"action": action, "retry": False, "dead_letter": action == "DO_NOT_REPOST",
                "next_retry_at": None}
    if attempt >= max_attempts:
        return {"action": "DEAD_LETTER", "retry": False, "dead_letter": True, "next_retry_at": None}
    delay = backoff_seconds(attempt, retry_after if action == "RETRY_AFTER" else None)
    return {
        "action": action,
        "retry": True,
        "dead_letter": False,
        "next_retry_at": datetime.now(timezone.utc) + timedelta(seconds=delay),
        "delay_seconds": delay,
    }
