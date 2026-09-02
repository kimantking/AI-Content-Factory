from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.base import session_scope
from app.db.models import OpsAlert, Publication, PublishJob
from app.ops import health as _health
from app.ops.alerts import raise_alert
from app.ops.cost_anomaly import check_cost_anomaly
from app.ops.runtime_flags import (
    FLAG_EMERGENCY_STOP,
    FLAG_MAINTENANCE_MODE,
    FLAG_SAFE_MODE,
    emergency_stop_active,
    set_flag,
)
from app.ops.storage_integrity import scan_assets
from app.publishing.webhooks import apply_webhook

pytestmark = pytest.mark.integration


# ---- emergency stop persists across "restart" ------------------------ #

def test_emergency_stop_is_persistent(_ops_defaults):
    _ops_defaults.autopilot_emergency_stop = False           # in-process hint cleared (like a restart)
    set_flag(FLAG_EMERGENCY_STOP, {"enabled": True}, actor="user")
    from app.ops.runtime_flags import _CACHE

    _CACHE.clear()
    assert emergency_stop_active() is True
    from app.autopilot.controller import run_autopilot

    assert run_autopilot("FULL_AUTO")["status"] == "STOPPED"
    set_flag(FLAG_EMERGENCY_STOP, {"enabled": False}, actor="user")


def test_safe_mode_blocks_autopilot_production(_ops_defaults):
    set_flag(FLAG_SAFE_MODE, {"enabled": True}, actor="user")
    from app.ops.runtime_flags import _CACHE

    _CACHE.clear()
    from app.autopilot.controller import run_autopilot

    r = run_autopilot("FULL_AUTO")
    assert r["status"] == "HOLD" and "SAFE_MODE" in r["reason"]
    set_flag(FLAG_SAFE_MODE, {"enabled": False}, actor="user")


def test_maintenance_mode_returns_503(_ops_defaults):
    from app.main import app

    c = TestClient(app, raise_server_exceptions=False)
    set_flag(FLAG_MAINTENANCE_MODE, {"enabled": True}, actor="user")
    from app.ops.runtime_flags import _CACHE

    _CACHE.clear()
    try:
        assert c.get("/api/config").status_code == 503
        assert c.get("/health/live").status_code == 200        # health still passes
    finally:
        set_flag(FLAG_MAINTENANCE_MODE, {"enabled": False}, actor="user")
        _CACHE.clear()


# ---- dependency failure -> readiness, not liveness ------------------ #

def test_database_down_flips_readiness_not_liveness(monkeypatch):
    monkeypatch.setattr(_health, "check_database", lambda: {"status": "DOWN", "error": "sim"})
    r = _health.readiness()
    assert r["ready"] is False
    assert _health.liveness()["status"] == "alive"


def test_redis_down_degrades_readiness(monkeypatch):
    monkeypatch.setattr(_health, "check_redis", lambda: {"status": "DOWN", "error": "sim"})
    assert _health.readiness()["ready"] is False


# ---- storage integrity ------------------------------------------- #

def test_storage_integrity_flags_missing_and_corrupted(tmp_path, _ops_defaults):
    import uuid

    from app.db.models import Asset, Campaign

    cid = str(uuid.uuid4())
    good = tmp_path / "good.png"
    good.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 100)
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"")
    with session_scope() as s:
        s.add(Campaign(id=cid, topic="t", platforms=["youtube_shorts"], status="SUCCESS"))
        s.flush()
        s.add(Asset(campaign_id=cid, asset_type="render", storage_path=str(good), status="SUCCESS"))
        s.add(Asset(campaign_id=cid, asset_type="image", storage_path=str(bad), status="SUCCESS"))
        s.add(Asset(campaign_id=cid, asset_type="thumbnail",
                    storage_path=str(tmp_path / "nope.png"), status="SUCCESS"))
    res = scan_assets()
    assert len(res["missing"]) == 1 and len(res["corrupted"]) == 1 and res["ok"] == 1
    with session_scope() as s:
        statuses = {a.storage_path.split("\\")[-1].split("/")[-1]: a.status
                    for a in s.query(Asset).filter_by(campaign_id=cid)}
    assert statuses["bad.png"] == "CORRUPTED"
    assert statuses["nope.png"] == "MISSING_ASSET"


# ---- webhook replay -------------------------------------------- #

def test_signed_webhook_replay_does_not_double_transition():
    import uuid

    from app.db.models import Campaign

    cid = str(uuid.uuid4())
    with session_scope() as s:
        s.add(Campaign(id=cid, topic="t", platforms=["x"], status="SUCCESS"))
        s.flush()
        job = PublishJob(campaign_id=cid, platform="x", status="VERIFYING",
                         idempotency_key=str(uuid.uuid4()))
        s.add(job)
        s.flush()
        s.add(Publication(publish_job_id=job.id, campaign_id=cid, platform="x",
                          status="VERIFYING", remote_post_id="rp-777"))
    payload = {"remote_post_id": "rp-777", "status": "PUBLISHED"}
    with session_scope() as s:
        r1 = apply_webhook(s, "x", payload, verified=True)
    with session_scope() as s:
        r2 = apply_webhook(s, "x", payload, verified=True)      # exact replay
    assert r1.get("matched") and not r1.get("duplicate")
    assert r2.get("duplicate") is True
    from app.db.models import PublicationEvent

    with session_scope() as s:
        n = s.query(PublicationEvent).filter_by(event="WEBHOOK_PUBLISHED").count()
    assert n == 1                                              # only one transition recorded


# ---- cost anomaly + alert dedup ------------------------------ #

def test_cost_anomaly_detects_spike(_ops_defaults):
    import uuid

    from app.db.models import Campaign, CostLog

    _ops_defaults.cost_anomaly_factor = 3.0
    with session_scope() as s:
        for i in range(6):
            c = str(uuid.uuid4())
            s.add(Campaign(id=c, topic=f"n{i}", platforms=["x"], status="SUCCESS"))
            s.flush()
            s.add(CostLog(campaign_id=c, agent_name="a", kind="LLM", provider="mock",
                          amount_usd=1.0))
        spike = str(uuid.uuid4())
        s.add(Campaign(id=spike, topic="spike", platforms=["x"], status="SUCCESS"))
        s.flush()
        s.add(CostLog(campaign_id=spike, agent_name="a", kind="LLM", provider="mock",
                      amount_usd=20.0))
        spike_id = spike
    res = check_cost_anomaly(campaign_id=spike_id)
    assert res["anomaly"] is True
    assert any(f["scope"] == "campaign" for f in res["findings"])


def test_alert_dedup(_ops_defaults):
    a1 = raise_alert("HIGH", "test_dedup", "boom", {"resource_id": "r1"})
    a2 = raise_alert("HIGH", "test_dedup", "boom again", {"resource_id": "r1"})
    assert a1["notified"] is True
    assert a2["notified"] is False and a2["count"] == 2         # deduped within cooldown
    with session_scope() as s:
        assert s.query(OpsAlert).filter_by(key="test_dedup", status="OPEN").count() == 1
