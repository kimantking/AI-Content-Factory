from __future__ import annotations

import threading

import pytest

from app.db.base import session_scope
from app.mb import budget as B


def test_hierarchical_hard_budget(workspace_a):
    ws = workspace_a["workspace_id"]
    b = workspace_a["brand_id"]
    c1 = workspace_a["channel1_id"]      # daily_budget 25
    with session_scope() as db:
        # channel hard limit is 25 -> a 20 reservation is fine, a further 10 is not
        r1 = B.reserve(db, workspace_id=ws, brand_id=b, channel_id=c1, amount_usd=20.0)
        assert r1.status == "RESERVED"
        with pytest.raises(B.BudgetReservationError) as ei:
            B.reserve(db, workspace_id=ws, brand_id=b, channel_id=c1, amount_usd=10.0)
        assert ei.value.scope == "CHANNEL"

    # brand limit is 70 -> two channels at 25 + 20 is fine; pushing brand over 70 fails
    with session_scope() as db:
        B.reserve(db, workspace_id=ws, brand_id=b, channel_id=workspace_a["channel2_id"], amount_usd=20.0)
        # brand now at 40; a 35 more on channel2 (limit 20) fails at CHANNEL first
        with pytest.raises(B.BudgetReservationError):
            B.reserve(db, workspace_id=ws, brand_id=b, channel_id=workspace_a["channel2_id"], amount_usd=35.0)


def test_workspace_hard_budget_and_release(workspace_a):
    ws = workspace_a["workspace_id"]   # workspace daily hard 100
    with session_scope() as db:
        r = B.reserve(db, workspace_id=ws, amount_usd=90.0)
        with pytest.raises(B.BudgetReservationError) as ei:
            B.reserve(db, workspace_id=ws, amount_usd=20.0)
        assert ei.value.scope == "WORKSPACE"
        B.release(db, r.id)
    with session_scope() as db:
        # after release, budget is free again
        r2 = B.reserve(db, workspace_id=ws, amount_usd=20.0)
        assert r2.status == "RESERVED"
        usage = B.day_usage(db, workspace_id=ws)
        assert usage["total_reserved_usd"] == pytest.approx(20.0)


def test_settle_uses_actual_cost(workspace_a):
    ws = workspace_a["workspace_id"]
    with session_scope() as db:
        r = B.reserve(db, workspace_id=ws, amount_usd=40.0)
        B.settle(db, r.id, actual_usd=12.0)
        assert B.day_usage(db, workspace_id=ws)["total_reserved_usd"] == pytest.approx(12.0)


def test_concurrent_reservations_cannot_exceed_hard_limit(workspace_a):
    """Two threads each try to reserve 60 against a 100 hard limit; exactly one
    must fail (transactional row-lock serialises them)."""
    ws = workspace_a["workspace_id"]
    results: list[str] = []
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        try:
            with session_scope() as db:
                B.reserve(db, workspace_id=ws, amount_usd=60.0)
            results.append("ok")
        except B.BudgetReservationError:
            results.append("blocked")
        except Exception as e:  # noqa: BLE001
            results.append(f"error:{e}")

    ts = [threading.Thread(target=worker) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=20)

    assert sorted(results) == ["blocked", "ok"], results
    with session_scope() as db:
        assert B.day_usage(db, workspace_id=ws)["total_reserved_usd"] == pytest.approx(60.0)


def test_budget_hierarchy_validation(workspace_a):
    from app.db.models_mb import Channel

    with session_scope() as db:
        # push channel limits above the brand limit
        for cid in (workspace_a["channel1_id"], workspace_a["channel2_id"]):
            db.get(Channel, cid).daily_budget_usd = 50.0   # 100 total > brand 70
        problems = B.validate_hierarchy(db, workspace_a["workspace_id"])
        assert any("brand" in p for p in problems)
