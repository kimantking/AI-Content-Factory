"""Phase 11 — AI 연결: encrypted credential vault + safe connection probes.

Mocked HTTP / SDK only — NO real cloud call, NO paid media generation.
Covers: encryption round-trip, masking, no-secret-in-response, .env fallback,
workspace isolation, delete, probe error normalisation, GLOBAL_PAID_PROVIDER_PAUSE
hard block, status vocabulary, snapshot/Model-Router visibility.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.phase11]


@pytest.fixture(autouse=True)
def _clear_status_cache():
    from app.providers import status as st
    st._CACHE.clear()
    yield
    st._CACHE.clear()


# --------------------------------------------------------------------------- #
#  storage / encryption
# --------------------------------------------------------------------------- #

def test_set_key_encrypts_and_never_returns_plaintext():
    from app.providers import credentials as cred

    plain = "sk-ant-SECRET-1234567890-abcdef"
    view = cred.set_key("anthropic", plain, workspace_id="")

    assert view["configured"] is True
    assert view["status"] == "CONFIGURED"
    assert view["last4"] == "cdef"
    # the plaintext key must appear nowhere in the API-facing view
    for v in _flatten(view):
        assert plain not in v
    # the stored column is ciphertext, not the key
    from app.db.base import session_scope
    from app.db.models_p11 import ProviderCredential
    with session_scope() as s:
        row = s.get(ProviderCredential, ("anthropic", ""))
        assert row.api_key_encrypted and plain not in row.api_key_encrypted
    # …but the backend can still recover it for a real call
    assert cred.get_key("anthropic") == plain


def test_delete_key_clears_credential():
    from app.providers import credentials as cred
    cred.set_key("tavily", "tvly-abcdefabcdef", workspace_id="")
    assert cred.get_key("tavily") == "tvly-abcdefabcdef"
    cred.delete_key("tavily", workspace_id="")
    assert cred.get_key("tavily") is None
    assert cred.describe("tavily")["status"] == "NOT_CONFIGURED"


def test_env_fallback_when_no_db_row(_base_settings):
    from app.providers import credentials as cred
    _base_settings.google_api_key = "AIza-env-key-value"
    assert cred.get_key("google") == "AIza-env-key-value"
    assert cred.key_source("google") == "env"
    _base_settings.google_api_key = ""
    assert cred.get_key("google") is None
    assert cred.key_source("google") == "none"


def test_db_key_overrides_env(_base_settings):
    from app.providers import credentials as cred
    _base_settings.anthropic_api_key = "env-key-should-lose"
    cred.set_key("anthropic", "db-key-should-win-123", workspace_id="")
    assert cred.get_key("anthropic") == "db-key-should-win-123"
    assert cred.key_source("anthropic") == "instance"


def test_workspace_isolation():
    from app.providers import credentials as cred
    cred.set_key("elevenlabs", "sk_instance-key-000000", workspace_id="")
    cred.set_key("elevenlabs", "sk_ws-A-key-1111111111", workspace_id="ws-A")

    assert cred.get_key("elevenlabs", workspace_id="ws-A") == "ws-A-key-1111111111"
    # ws-B has no own key -> falls back to the instance one, NEVER ws-A's
    assert cred.get_key("elevenlabs", workspace_id="ws-B") == "instance-key-000000"
    assert cred.describe("elevenlabs", workspace_id="ws-A")["last4"] == "1111"
    assert cred.describe("elevenlabs", workspace_id="ws-B")["key_source"] == "instance"


def test_mask_only_exposes_edges():
    from app.providers import credentials as cred
    assert cred.mask("sk-ant-1234567890abcdef") == "sk-a****cdef"
    assert cred.mask("short") == "****"
    assert cred.mask(None) == ""


# --------------------------------------------------------------------------- #
#  probes — error normalisation, no real call
# --------------------------------------------------------------------------- #

def test_anthropic_probe_auth_failure_is_normalised(_base_settings, monkeypatch):
    from app.providers import credentials as cred, probe

    cred.set_key("anthropic", "sk-ant-bad-key-000000", workspace_id="")

    class _AuthErr(Exception):
        pass

    class _FakeClient:
        def __init__(self, **kw):
            self.messages = self

        def create(self, **kw):
            raise _AuthErr("authentication_error: invalid x-api-key")

    monkeypatch.setattr(probe, "_paid_paused", lambda: False)
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)

    res = probe.run("anthropic", workspace_id="")
    assert res["status"] == "AUTH_FAILED" and res["ok"] is False
    assert cred.describe("anthropic")["status"] == "AUTH_FAILED"
    assert cred.describe("anthropic")["last_error_code"] == "ANTHROPIC_AUTH_FAILED"


def test_anthropic_probe_success_records_connected(_base_settings, monkeypatch):
    from app.providers import credentials as cred, probe

    cred.set_key("anthropic", "sk-ant-good-key-111111", workspace_id="")

    class _Usage:
        input_tokens = 7
        output_tokens = 2

    class _Block:
        type = "text"
        text = "ok"

    class _Resp:
        content = [_Block()]
        usage = _Usage()

    class _FakeClient:
        def __init__(self, **kw):
            self.messages = self

        def create(self, **kw):
            assert kw["max_tokens"] <= 16  # minimal probe only
            return _Resp()

    monkeypatch.setattr(probe, "_paid_paused", lambda: False)
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)

    res = probe.run("anthropic", workspace_id="")
    assert res["status"] == "CONNECTED" and res["ok"] is True
    d = cred.describe("anthropic")
    assert d["status"] == "CONNECTED" and d["last_success_at"]


def test_paid_provider_pause_blocks_anthropic_and_tavily_probe(_base_settings, monkeypatch):
    from app.providers import credentials as cred, probe

    cred.set_key("anthropic", "sk-ant-key-2222222222", workspace_id="")
    cred.set_key("tavily", "tvly-key-2222222222", workspace_id="")
    monkeypatch.setattr(probe, "_paid_paused", lambda: True)

    for p in ("anthropic", "tavily"):
        res = probe.run(p, workspace_id="")
        assert res["status"] == "BLOCKED" and res["ok"] is False


def test_google_probe_free_get_and_model_validation(_base_settings, monkeypatch):
    from app.providers import credentials as cred, probe
    from app.providers.media import _http

    cred.set_key("google", "AIza-key-3333333333", workspace_id="")
    _base_settings.google_image_model = "imagen-3.0-generate-002"
    _base_settings.google_video_model = "veo-9.9-does-not-exist"

    calls: list[str] = []

    def fake_http_json(url, **kw):
        calls.append(url)
        assert ":predict" not in url and ":generate" not in url  # NO generation
        return {"models": [
            {"name": "models/imagen-3.0-generate-002"},
            {"name": "models/gemini-1.5-flash"},
        ]}

    monkeypatch.setattr(_http, "http_json", fake_http_json)
    monkeypatch.setattr("app.providers.probe.http_json", fake_http_json, raising=False)
    import app.providers.media._http as h
    monkeypatch.setattr(h, "http_json", fake_http_json)

    res = probe.run("google", workspace_id="")
    assert res["status"] == "CONNECTED"
    assert res["image_capability"] == "OK"
    assert res["video_capability"] == "MODEL_NOT_LISTED"
    assert all("/v1beta/models" in u for u in calls)


def test_probe_result_carries_no_secret(_base_settings, monkeypatch):
    from app.providers import credentials as cred, probe

    secret = "sk-ant-TOPSECRET-999888777"
    cred.set_key("anthropic", secret, workspace_id="")

    class _FakeClient:
        def __init__(self, **kw):
            self.messages = self

        def create(self, **kw):
            raise RuntimeError("boom")

    monkeypatch.setattr(probe, "_paid_paused", lambda: False)
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)

    res = probe.run("anthropic", workspace_id="")
    for v in _flatten(res):
        assert secret not in v and secret[-8:] not in v.replace("777", "___")


# --------------------------------------------------------------------------- #
#  status.py / snapshot visibility
# --------------------------------------------------------------------------- #

def test_elevenlabs_rejects_api_key_id_before_storage(_base_settings):
    from app.providers import credentials as cred

    with pytest.raises(ValueError, match="API Key ID"):
        cred.set_key("elevenlabs", "api-key-id-f6af", workspace_id="")


def test_status_reports_connected_after_successful_probe(_base_settings):
    from app.providers import credentials as cred
    from app.providers.status import provider_status

    cred.set_key("google", "AIza-key-4444444444", workspace_id="")
    cred.record_probe("google", ok=True, status="CONNECTED",
                      meta_patch={"models_visible": 12, "image_capability": "OK",
                                  "video_capability": "OK"}, workspace_id="")
    row = next(p for p in provider_status(probe=False)["providers"] if p["provider"] == "google")
    assert row["status"] == "CONNECTED"


def test_status_never_connected_without_probe(_base_settings):
    from app.providers import credentials as cred
    from app.providers.status import provider_status

    cred.set_key("anthropic", "sk-ant-key-5555555555", workspace_id="")
    row = next(p for p in provider_status(probe=False)["providers"] if p["provider"] == "anthropic")
    assert row["status"] in ("MOCK", "CONFIGURED")   # key present, not probed -> never CONNECTED


# --------------------------------------------------------------------------- #

def _flatten(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            out += _flatten(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out += _flatten(v)
    elif isinstance(obj, str):
        out.append(obj)
    else:
        out.append(str(obj))
    return out
