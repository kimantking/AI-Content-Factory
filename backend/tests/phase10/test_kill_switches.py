"""Phase 10 §14, §22, §40, §89 — production kill switches wired to real backend
gates. GLOBAL_PUBLISH_PAUSE → 0 remote publish; GLOBAL_PAID_PROVIDER_PAUSE → 0
cloud/paid provider calls, local Ollama/mock still allowed. DB-backed → survive a
process restart."""
from __future__ import annotations

import uuid

import pytest

from app.db.base import session_scope
from app.db.models import Campaign, PublishJob
from app.ops.runtime_flags import (
    FLAG_PAID_PROVIDER_PAUSE, FLAG_PUBLISH_PAUSE, _CACHE, paid_provider_paused,
    publish_paused, set_flag,
)

pytestmark = [pytest.mark.phase10]


@pytest.fixture(autouse=True)
def _clear_flag_cache():
    _CACHE.clear()
    yield
    _CACHE.clear()


def _mk_ready_job(platform="naver_blog"):
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="kill-switch", audience_goal="BALANCED",
                        platforms=[platform], status="SUCCESS"))
        db.flush()
        j = PublishJob(campaign_id=cid, platform=platform, content_type="post",
                       status="READY", run_mode="MANUAL", approval_status="APPROVED",
                       idempotency_key=str(uuid.uuid4()))
        db.add(j)
        db.flush()
        return j.id


def test_publish_pause_blocks_remote_and_is_reversible():
    from app.publishing.engine import run_publish_job
    jid = _mk_ready_job()

    set_flag(FLAG_PUBLISH_PAUSE, {"enabled": True}, actor="test")
    _CACHE.clear()
    assert publish_paused() is True
    res = run_publish_job(jid)
    assert res.get("publish_paused") is True
    with session_scope() as db:
        job = db.get(PublishJob, jid)
        assert job.remote_post_id is None
        assert job.status == "READY"                 # runnable, not failed

    # release → job proceeds again (naver_blog is MANUAL_ONLY so no remote post,
    # but it is no longer short-circuited by the pause)
    set_flag(FLAG_PUBLISH_PAUSE, {"enabled": False}, actor="test")
    _CACHE.clear()
    assert publish_paused() is False
    res2 = run_publish_job(jid)
    assert res2.get("publish_paused") is not True


def test_publish_pause_survives_a_fresh_flag_read():
    """DB-backed → a 'process restart' (cache cleared) still sees it enabled."""
    set_flag(FLAG_PUBLISH_PAUSE, {"enabled": True}, actor="test")
    _CACHE.clear()                                   # simulate restart
    assert publish_paused() is True


def test_paid_provider_pause_blocks_cloud_but_not_local(monkeypatch, _base_settings):
    _base_settings.allow_cloud_fallback = True
    monkeypatch.setattr(_base_settings, "anthropic_api_key", "k", raising=False)
    from app.ai_router import execute as ex
    from app.providers.errors import ProviderError

    set_flag(FLAG_PAID_PROVIDER_PAUSE, {"enabled": True}, actor="test")
    _CACHE.clear()
    assert paid_provider_paused() is True

    # cloud provider construction is refused
    with pytest.raises(ProviderError):
        ex._provider_for("claude-sonnet-5", "anthropic")

    # local + mock still work
    assert type(ex._provider_for("gemma3:4b", "ollama")).__name__ == "OllamaLLMProvider"
    assert type(ex._provider_for("mock", "mock")).__name__ == "MockLLMProvider"

    set_flag(FLAG_PAID_PROVIDER_PAUSE, {"enabled": False}, actor="test")
    _CACHE.clear()


def test_toggle_endpoint_accepts_the_new_flags():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, raise_server_exceptions=False)

    r = c.post("/api/ops/flags/GLOBAL_PUBLISH_PAUSE", json={"enabled": True, "confirm": True})
    assert r.status_code == 200 and r.json()["enabled"] is True
    r = c.post("/api/ops/flags/GLOBAL_PAID_PROVIDER_PAUSE", json={"enabled": True, "confirm": True})
    assert r.status_code == 200
    # enabling without confirm is refused
    r = c.post("/api/ops/flags/GLOBAL_PUBLISH_PAUSE", json={"enabled": True})
    assert r.status_code == 400
    _CACHE.clear()
    r = c.post("/api/ops/flags/GLOBAL_PUBLISH_PAUSE", json={"enabled": False, "confirm": True})
    assert r.status_code == 200


def test_emergency_stop_also_pauses_publish():
    from app.ops.runtime_flags import FLAG_EMERGENCY_STOP
    from app.publishing.engine import run_publish_job
    jid = _mk_ready_job()
    set_flag(FLAG_EMERGENCY_STOP, {"enabled": True}, actor="test")
    _CACHE.clear()
    res = run_publish_job(jid)
    assert res.get("publish_paused") is True and res.get("reason") == "EMERGENCY_STOP"
    with session_scope() as db:
        assert db.get(PublishJob, jid).remote_post_id is None
    set_flag(FLAG_EMERGENCY_STOP, {"enabled": False}, actor="test")
    _CACHE.clear()
