"""Hierarchical hard budgets + transactional reservation (§22-§25, §108).

Workspace ⊇ Brand ⊇ Channel ⊇ Campaign. A reservation is taken *before* a campaign
runs and settled to the actual cost afterwards (or released on cancel). Concurrent
workers cannot collectively exceed a hard limit because the check + insert happen
inside one transaction that locks the day's rows for the scope.
"""
from __future__ import annotations

import zlib
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models_mb import (
    Brand,
    BudgetAllocation,
    BudgetReservation,
    Channel,
    Workspace,
)


class BudgetReservationError(RuntimeError):
    def __init__(self, scope: str, limit: float, would_be: float):
        super().__init__(f"{scope} daily hard budget exceeded: {would_be:.2f} > {limit:.2f}")
        self.scope = scope
        self.limit = limit
        self.would_be = would_be
        self.error_type = "BUDGET_EXCEEDED"


def _today(ws_tz: str = "UTC") -> str:
    return datetime.now(timezone.utc).date().isoformat()


def hard_limits(db: Session, *, workspace_id: str, brand_id: str | None,
                channel_id: str | None) -> dict[str, float]:
    """Effective daily hard limit for each level (0 = unlimited/unset)."""
    out: dict[str, float] = {}
    ws = db.get(Workspace, workspace_id)
    out["WORKSPACE"] = float(ws.daily_hard_budget_usd) if ws else 0.0
    if brand_id:
        b = db.get(Brand, brand_id)
        out["BRAND"] = float(b.daily_hard_budget_usd) if b else 0.0
    if channel_id:
        c = db.get(Channel, channel_id)
        out["CHANNEL"] = float(c.daily_budget_usd) if c else 0.0
    # explicit BudgetAllocation rows override the model column when present
    for scope, sid in (("WORKSPACE", workspace_id), ("BRAND", brand_id), ("CHANNEL", channel_id)):
        if not sid:
            continue
        row = (db.query(BudgetAllocation)
               .filter_by(scope=scope, scope_id=sid, period="daily").first())
        if row and row.hard_limit_usd > 0:
            out[scope] = float(row.hard_limit_usd)
    return out


def _reserved_total(db: Session, *, day: str, column, value) -> float:
    q = select(func.coalesce(func.sum(BudgetReservation.amount_usd), 0.0)).where(
        BudgetReservation.day == day,
        BudgetReservation.status.in_(("RESERVED", "SETTLED")),
        column == value,
    )
    return float(db.execute(q).scalar_one())


def reserve(db: Session, *, workspace_id: str, amount_usd: float,
            brand_id: str | None = None, channel_id: str | None = None,
            campaign_id: str | None = None, day: str | None = None) -> BudgetReservation:
    """Atomically reserve `amount_usd` against every level's daily hard limit.

    Must be called inside an open transaction/session; the SELECT ... FOR UPDATE
    on the day's reservation rows serialises concurrent reservers for the same
    scope so their sum cannot exceed a hard limit.
    """
    if amount_usd < 0:
        raise ValueError("amount must be >= 0")
    day = day or _today()

    # Serialise ALL reservers for this (workspace, day). A transaction-scoped
    # Postgres advisory lock works even when no reservation rows exist yet, so it
    # closes the phantom-insert race that a `SELECT ... FOR UPDATE` on the (empty)
    # table would not. Auto-released on commit/rollback. Non-Postgres backends
    # (none in prod) silently skip the lock.
    key = zlib.crc32(f"budget:{workspace_id}:{day}".encode()) & 0x7FFFFFFF
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
    except Exception:  # noqa: BLE001 — not Postgres / advisory locks unavailable
        pass

    limits = hard_limits(db, workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id)

    checks = [("WORKSPACE", BudgetReservation.workspace_id, workspace_id)]
    if brand_id:
        checks.append(("BRAND", BudgetReservation.brand_id, brand_id))
    if channel_id:
        checks.append(("CHANNEL", BudgetReservation.channel_id, channel_id))

    for scope, col, val in checks:
        limit = limits.get(scope, 0.0)
        if limit <= 0:
            continue  # unset = unlimited
        current = _reserved_total(db, day=day, column=col, value=val)
        if current + amount_usd > limit + 1e-9:
            raise BudgetReservationError(scope, limit, current + amount_usd)

    res = BudgetReservation(
        workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id,
        campaign_id=campaign_id, day=day, amount_usd=round(amount_usd, 4),
        status="RESERVED",
    )
    db.add(res)
    db.flush()
    return res


def settle(db: Session, reservation_id: str, actual_usd: float) -> BudgetReservation | None:
    r = db.get(BudgetReservation, reservation_id)
    if r is None or r.status != "RESERVED":
        return r
    r.actual_usd = round(max(0.0, actual_usd), 4)
    r.amount_usd = r.actual_usd          # settled reservations count at actual cost
    r.status = "SETTLED"
    r.settled_at = datetime.now(timezone.utc)
    db.flush()
    return r


def release(db: Session, reservation_id: str) -> BudgetReservation | None:
    r = db.get(BudgetReservation, reservation_id)
    if r is None or r.status != "RESERVED":
        return r
    r.status = "RELEASED"
    r.amount_usd = 0.0
    r.settled_at = datetime.now(timezone.utc)
    db.flush()
    return r


def day_usage(db: Session, *, workspace_id: str, day: str | None = None) -> dict:
    day = day or _today()
    rows = (db.query(BudgetReservation)
            .filter_by(workspace_id=workspace_id, day=day)
            .filter(BudgetReservation.status.in_(("RESERVED", "SETTLED"))).all())
    by_channel: dict[str, float] = {}
    by_brand: dict[str, float] = {}
    total = 0.0
    for r in rows:
        total += r.amount_usd
        if r.channel_id:
            by_channel[r.channel_id] = by_channel.get(r.channel_id, 0.0) + r.amount_usd
        if r.brand_id:
            by_brand[r.brand_id] = by_brand.get(r.brand_id, 0.0) + r.amount_usd
    return {"day": day, "total_reserved_usd": round(total, 4),
            "by_channel": {k: round(v, 4) for k, v in by_channel.items()},
            "by_brand": {k: round(v, 4) for k, v in by_brand.items()},
            "hard_limit_usd": hard_limits(db, workspace_id=workspace_id,
                                          brand_id=None, channel_id=None).get("WORKSPACE", 0.0)}


def validate_hierarchy(db: Session, workspace_id: str) -> list[str]:
    """Child hard limits should not collectively exceed the parent (§23). Advisory."""
    problems: list[str] = []
    ws = db.get(Workspace, workspace_id)
    if not ws or ws.daily_hard_budget_usd <= 0:
        return problems
    brands = db.query(Brand).filter_by(workspace_id=workspace_id).all()
    brand_sum = sum(b.daily_hard_budget_usd for b in brands if b.daily_hard_budget_usd > 0)
    if brand_sum > ws.daily_hard_budget_usd + 1e-9:
        problems.append(f"brand daily limits sum {brand_sum:.0f} > workspace {ws.daily_hard_budget_usd:.0f}")
    for b in brands:
        if b.daily_hard_budget_usd <= 0:
            continue
        chans = db.query(Channel).filter_by(brand_id=b.id).all()
        csum = sum(c.daily_budget_usd for c in chans if c.daily_budget_usd > 0)
        if csum > b.daily_hard_budget_usd + 1e-9:
            problems.append(f"channel limits sum {csum:.0f} > brand '{b.name}' {b.daily_hard_budget_usd:.0f}")
    return problems
