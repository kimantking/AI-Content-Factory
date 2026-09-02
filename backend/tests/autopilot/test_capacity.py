"""AUDIT-P6-001 — cross-channel capacity planner: per-channel daily slots,
budget headroom, and the aggregate that caps an autopilot run."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.autopilot.capacity import channel_capacity, portfolio_capacity
from app.db.base import session_scope
from app.db.models import Campaign, CostLog
from app.db.models_mb import Brand, Channel, Workspace


def _ws(db):
    w = Workspace(id=str(uuid.uuid4()), name="W", slug=f"w-{uuid.uuid4().hex[:6]}")
    db.add(w)
    db.flush()
    b = Brand(id=str(uuid.uuid4()), workspace_id=w.id, name="B", slug=f"b-{uuid.uuid4().hex[:6]}")
    db.add(b)
    db.flush()
    return w, b


def _channel(db, w, b, *, name, maxp=3, budget=0.0, mode="FULL_AUTO"):
    ch = Channel(id=str(uuid.uuid4()), workspace_id=w.id, brand_id=b.id, name=name,
                 platform="youtube", channel_type="YOUTUBE_SHORTS", daily_max_posts=maxp,
                 daily_budget_usd=budget, autopilot_mode=mode, status="ACTIVE")
    db.add(ch)
    db.flush()
    return ch


def test_remaining_slots_decrement_with_todays_campaigns():
    with session_scope() as db:
        w, b = _ws(db)
        ch = _channel(db, w, b, name="C1", maxp=3)
        for _ in range(2):
            db.add(Campaign(id=str(uuid.uuid4()), topic="t", audience_goal="BALANCED",
                            platforms=["youtube_shorts"], status="RUNNING",
                            workspace_id=w.id, channel_id=ch.id))
        db.flush()
        rows = channel_capacity(db, workspace_id=w.id)
    assert rows[0]["used_today"] == 2
    assert rows[0]["remaining_slots"] == 1


def test_budget_headroom_blocks_channel():
    with session_scope() as db:
        w, b = _ws(db)
        ch = _channel(db, w, b, name="C2", maxp=5, budget=1.0)
        cid = str(uuid.uuid4())
        db.add(Campaign(id=cid, topic="t", audience_goal="BALANCED", platforms=["x"],
                        status="RUNNING", workspace_id=w.id, channel_id=ch.id))
        db.flush()
        db.add(CostLog(campaign_id=cid, agent_name="x", kind="LLM", amount_usd=1.5))
        db.flush()
        rows = channel_capacity(db, workspace_id=w.id)
    assert rows[0]["spent_today_usd"] >= 1.5
    assert rows[0]["budget_blocked"] is True


def test_portfolio_capacity_aggregates_and_excludes_off_channels():
    with session_scope() as db:
        w, b = _ws(db)
        _channel(db, w, b, name="A", maxp=2, mode="FULL_AUTO")
        _channel(db, w, b, name="B", maxp=4, mode="OFF")          # excluded
        _channel(db, w, b, name="C", maxp=3, budget=1.0, mode="FULL_AUTO")
        cid = str(uuid.uuid4())
        # spend past C's budget so C is blocked
        db.add(Campaign(id=cid, topic="t", audience_goal="BALANCED", platforms=["x"],
                        status="RUNNING", workspace_id=w.id,
                        channel_id=db.query(Channel).filter_by(name="C").one().id))
        db.flush()
        db.add(CostLog(campaign_id=cid, agent_name="x", kind="LLM", amount_usd=2.0))
        db.flush()
        cap = portfolio_capacity(db, workspace_id=w.id, fallback_max=99)
    assert cap["source"] == "channels"
    assert cap["max_new_campaigns"] == 2           # only channel A counts (B OFF, C blocked)
    assert cap["budget_blocked_channels"] == 1


def test_fallback_when_no_channels():
    with session_scope() as db:
        cap = portfolio_capacity(db, workspace_id=str(uuid.uuid4()), fallback_max=5)
    assert cap["source"] == "fallback" and cap["max_new_campaigns"] == 5


def test_capacity_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app

    with session_scope() as db:
        w, b = _ws(db)
        _channel(db, w, b, name="EP", maxp=2)
        wid = w.id
    r = TestClient(app).get("/api/publishing/calendar/capacity", params={"workspace_id": wid})
    assert r.status_code == 200
    assert r.json()["per_channel"][0]["name"] == "EP"
