"""Phase 11 — provider status endpoint, AI Support Snapshot integration, secret
redaction, config-check, and the invariants that must NOT regress."""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.db.base import session_scope
from app.main import app

pytestmark = [pytest.mark.phase11]
client = TestClient(app, raise_server_exceptions=False)

_GKEY = "AIza" + "S" * 35            # google-key-shaped, not real
_EKEY = "sk_" + "e" * 40            # elevenlabs-key-shaped, not real


@pytest.fixture(autouse=True)
def _clear_status_cache():
    from app.providers import status as st
    st._CACHE.clear()
    yield
    st._CACHE.clear()


def test_providers_endpoint_lists_all_five_without_secrets(_base_settings):
    _base_settings.google_api_key = _GKEY
    _base_settings.elevenlabs_api_key = _EKEY
    r = client.get("/api/providers", params={"probe": "false"})
    assert r.status_code == 200
    provs = {p["provider"] for p in r.json()["providers"]}
    assert provs == {"anthropic", "tavily", "google", "elevenlabs", "ollama"}
    blob = r.text
    assert _GKEY not in blob and _EKEY not in blob
    # key present but MOCK_MODE on (test default) -> MOCK, NEVER a false CONNECTED
    by = {p["provider"]: p["status"] for p in r.json()["providers"]}
    assert by["google"] == "MOCK" and by["elevenlabs"] == "MOCK"
    assert "CONNECTED" not in set(by.values())


def test_providers_not_configured_when_no_key(_base_settings):
    _base_settings.google_api_key = None
    _base_settings.elevenlabs_api_key = None
    r = client.get("/api/providers", params={"probe": "false"}).json()
    by = {p["provider"]: p["status"] for p in r["providers"]}
    assert by["google"] == "NOT_CONFIGURED" and by["elevenlabs"] == "NOT_CONFIGURED"


def test_snapshot_includes_google_and_elevenlabs_from_real_health(_base_settings):
    _base_settings.google_api_key = _GKEY
    _base_settings.elevenlabs_api_key = _EKEY
    from app.support.snapshot import build_snapshot
    with session_scope() as db:
        s = build_snapshot(db, admin=True)
    cs = s["system"]["cloud_providers"]
    assert cs["google_key_present"] is True and cs["elevenlabs_key_present"] is True
    provs = {p["provider"] for p in cs["providers"]}
    assert {"google", "elevenlabs"} <= provs
    # no secret anywhere in the snapshot
    blob = json.dumps(s, ensure_ascii=False)
    assert _GKEY not in blob and _EKEY not in blob


def test_config_check_reports_google_and_elevenlabs(_base_settings):
    _base_settings.mock_mode = False
    _base_settings.google_api_key = _GKEY
    _base_settings.image_provider = "google"
    _base_settings.elevenlabs_api_key = _EKEY
    _base_settings.tts_provider = "elevenlabs"
    _base_settings.elevenlabs_voice_id = "v1"
    from app.ops.config_check import check_config
    caps = check_config()["capabilities"]
    assert caps["GOOGLE_AI"]["status"] == "READY"
    assert caps["ELEVENLABS"]["status"] == "READY"
    assert caps["MEDIA_PROVIDERS"]["status"] == "READY"


def test_error_normaliser_maps_new_vendor_codes():
    from app.support.errors import normalise, suggested_action, is_retryable
    assert normalise("AUTH_ERROR", "GOOGLE_AUTH_FAILED: HTTP 403", "media") == "GOOGLE_AUTH_FAILED"
    assert normalise("RATE_LIMIT", "ELEVENLABS_RATE_LIMITED: HTTP 429", "tts") == "ELEVENLABS_RATE_LIMITED"
    assert normalise("AUTH_ERROR", "GOOGLE_NOT_CONFIGURED: no key", "") == "GOOGLE_NOT_CONFIGURED"
    assert "Google" in suggested_action("GOOGLE_AUTH_FAILED")
    assert is_retryable("GOOGLE_RATE_LIMITED") and not is_retryable("ELEVENLABS_NOT_CONFIGURED")


# ---- invariants that must NOT regress ---- #

def test_direct_provider_bypass_still_zero():
    from pathlib import Path
    app_dir = Path(__file__).resolve().parents[2] / "app"
    for rel in ("agents/nodes.py", "agents/media_nodes.py", "autopilot/pipeline.py"):
        src = (app_dir / rel).read_text(encoding="utf-8")
        assert not re.search(r"^[^#\n]*\bget_llm_provider\s*\(", src, re.M), rel


def test_existing_providers_unchanged(_base_settings):
    """Anthropic / Tavily / Ollama selection is not affected by the new keys."""
    from app.providers.registry import get_llm_provider, get_search_provider
    _base_settings.google_api_key = _GKEY
    _base_settings.elevenlabs_api_key = _EKEY
    # mock mode still yields the mock providers
    assert type(get_llm_provider()).__name__ == "MockLLMProvider"
    assert "Mock" in type(get_search_provider()).__name__


def test_paid_provider_pause_falls_media_back_to_mock(_base_settings):
    from app.ops.runtime_flags import FLAG_PAID_PROVIDER_PAUSE, _CACHE, set_flag
    from app.providers.media import registry
    _base_settings.mock_mode = False
    _base_settings.google_api_key = _GKEY
    _base_settings.image_provider = "google"
    _base_settings.video_provider = "google"
    _base_settings.elevenlabs_api_key = _EKEY
    _base_settings.tts_provider = "elevenlabs"
    _base_settings.elevenlabs_voice_id = "v"
    assert type(registry.get_image_provider()).__name__ == "GoogleImageProvider"

    set_flag(FLAG_PAID_PROVIDER_PAUSE, {"enabled": True}, actor="test")
    _CACHE.clear()
    try:
        assert type(registry.get_image_provider()).__name__ == "MockImageProvider"
        assert registry.get_video_provider() is None
        assert type(registry.get_tts_provider()).__name__ == "MockTTSProvider"
    finally:
        set_flag(FLAG_PAID_PROVIDER_PAUSE, {"enabled": False}, actor="test")
        _CACHE.clear()


def test_learn_only_still_generates_no_media(_base_settings):
    """LEARN_ONLY must produce 0 media regardless of which media provider is set."""
    import uuid
    from app.db.models import Asset, Campaign, MediaTask
    from app.intel import fetch as F
    from app.intel.engine import add_urls, run_learning_job
    _base_settings.google_api_key = _GKEY
    _base_settings.image_provider = "google"
    c = F.MockReferenceClient()
    for i in range(4):
        c.register(f"https://p11.example.com/a{i}",
                   body=f"<html><head><title>t{i}</title></head><body><main><h1>t{i}</h1>"
                        f"<p>연구에 따르면 자동화가 {40 + i}% 라고 한다. 전문가는 검수가 중요하다 말했다. "
                        f"예시 {i}에서 사람이 확인한다.</p></main></body></html>")
    F.set_client(c)
    ws = str(uuid.uuid4())
    try:
        with session_scope() as db:
            j = add_urls(db, urls=[f"https://p11.example.com/a{i}" for i in range(4)],
                         execution_mode="LEARN_ONLY", workspace_id=ws, topic="t")
            jid = j.id
        with session_scope() as db:
            run_learning_job(db, jid)
        with session_scope() as db:
            assert db.query(Campaign).filter_by(workspace_id=ws).count() == 0
            assert db.query(Asset).count() == 0 and db.query(MediaTask).count() == 0
    finally:
        F.set_client(F.MockReferenceClient())
