from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Protocol

SEVERITIES = ["INFO", "WARNING", "HIGH", "CRITICAL"]
_COOLDOWN = {"INFO": 3600, "WARNING": 900, "HIGH": 300, "CRITICAL": 120}


class NotificationProvider(Protocol):
    name: str

    def notify(self, alert: dict) -> None: ...


class DashboardNotifier:
    name = "dashboard"

    def notify(self, alert: dict) -> None:  # the alert row itself IS the dashboard feed
        return None


_notifiers: list[NotificationProvider] = [DashboardNotifier()]


def register_notifier(n: NotificationProvider) -> None:
    _notifiers.append(n)


def _fingerprint(key: str, detail: dict) -> str:
    salient = {k: detail.get(k) for k in ("resource_id", "platform", "provider", "queue")}
    return hashlib.sha256(f"{key}|{salient}".encode()).hexdigest()[:32]


def raise_alert(severity: str, key: str, message: str, detail: dict | None = None) -> dict:
    """Deduplicated alert. Repeat firings within the cooldown bump `count` and
    `last_seen` instead of creating a new row / notification."""
    assert severity in SEVERITIES, severity
    detail = detail or {}
    fp = _fingerprint(key, detail)
    from app.db.base import session_scope
    from app.db.models import OpsAlert

    now = datetime.now(timezone.utc)
    with session_scope() as s:
        existing = (s.query(OpsAlert)
                    .filter_by(fingerprint=fp, status="OPEN")
                    .order_by(OpsAlert.last_seen.desc()).first())
        if existing:
            prev = existing.last_seen
            prev = prev.replace(tzinfo=timezone.utc) if prev.tzinfo is None else prev
            gap = (now - prev).total_seconds()
            existing.count += 1
            existing.last_seen = now
            existing.message = message
            row = existing
            fired = gap >= _COOLDOWN[severity]      # re-notify only after the cooldown
        else:
            row = OpsAlert(severity=severity, key=key, fingerprint=fp, message=message,
                           detail=detail, count=1, first_seen=now, last_seen=now)
            s.add(row)
            fired = True
        s.flush()
        payload = {"id": row.id, "severity": severity, "key": key, "message": message,
                   "fingerprint": fp, "count": row.count, "detail": detail}

    if fired:
        for n in _notifiers:
            try:
                n.notify(payload)
            except Exception:  # noqa: BLE001
                pass
    return {**payload, "notified": fired}


def resolve_alert(alert_id: str, actor: str = "system") -> bool:
    from app.db.base import session_scope
    from app.db.models import OpsAlert

    with session_scope() as s:
        row = s.get(OpsAlert, alert_id)
        if not row:
            return False
        row.status = "RESOLVED"
        row.resolved_at = datetime.now(timezone.utc)
    return True


def open_alerts(limit: int = 100) -> list[dict]:
    from app.db.base import session_scope
    from app.db.models import OpsAlert

    with session_scope() as s:
        rows = (s.query(OpsAlert).filter_by(status="OPEN")
                .order_by(OpsAlert.last_seen.desc()).limit(limit).all())
        return [{"id": r.id, "severity": r.severity, "key": r.key, "message": r.message,
                 "count": r.count, "first_seen": r.first_seen.isoformat(),
                 "last_seen": r.last_seen.isoformat(), "detail": r.detail} for r in rows]
