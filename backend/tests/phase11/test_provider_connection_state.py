"""Phase 11 follow-up — provider connection-state verification. In MOCK_MODE with
no keys, NOTHING may report CONNECTED. Ollama that is running but disabled in
config reports DEGRADED (honest), never CONNECTED."""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.phase11]


@pytest.fixture(autouse=True)
def _clear(monkeypatch):
    from app.providers import status as st
    st._CACHE.clear()
    yield
    st._CACHE.clear()


def test_mock_mode_no_keys_nothing_is_connected(_base_settings):
    """The default dev config (mock_mode=true, no keys) must not fake a CONNECTED."""
    _base_settings.mock_mode = True
    _base_settings.anthropic_api_key = None
    _base_settings.tavily_api_key = None
    _base_settings.google_api_key = None
    _base_settings.elevenlabs_api_key = None
    _base_settings.ollama_enabled = False
    from app.providers.status import provider_status

    # offline view
    off = {p["provider"]: p["status"] for p in provider_status(probe=False)["providers"]}
    assert all(v == "NOT_CONFIGURED" for v in off.values()), off

    # live probe view — none may be CONNECTED
    live = {p["provider"]: p["status"] for p in provider_status(probe=True)["providers"]}
    assert "CONNECTED" not in set(live.values()) - {"ollama"} or live.get("anthropic") != "CONNECTED"
    for prov in ("anthropic", "tavily", "google", "elevenlabs"):
        assert live[prov] == "NOT_CONFIGURED", (prov, live[prov])


def test_key_present_but_mock_mode_reports_MOCK_not_connected(_base_settings):
    """MOCK_MODE=true with keys set must show MOCK, never CONNECTED."""
    _base_settings.mock_mode = True
    _base_settings.anthropic_api_key = "k-anth"
    _base_settings.tavily_api_key = "k-tav"
    _base_settings.google_api_key = "k-goog"
    _base_settings.elevenlabs_api_key = "k-11"
    from app.providers.status import provider_status
    for probe in (True, False):
        st = {p["provider"]: p["status"] for p in provider_status(probe=probe)["providers"]}
        assert st["anthropic"] == "MOCK", (probe, st)
        assert st["tavily"] == "MOCK"
        assert st["google"] == "MOCK"
        assert st["elevenlabs"] == "MOCK"
        assert "CONNECTED" not in {st["anthropic"], st["tavily"], st["google"], st["elevenlabs"]}


def test_key_present_not_mock_reports_CONFIGURED_not_connected(_base_settings):
    """Anthropic/Tavily have no free probe: key + not-mock -> CONFIGURED, never a
    fake CONNECTED (we do NOT spend a paid call to check)."""
    _base_settings.mock_mode = False
    _base_settings.llm_provider = "anthropic"
    _base_settings.search_provider = "tavily"
    _base_settings.anthropic_api_key = "k-anth"
    _base_settings.tavily_api_key = "k-tav"
    from app.providers.status import provider_status
    st = {p["provider"]: p["status"] for p in provider_status(probe=True)["providers"]}
    assert st["anthropic"] == "CONFIGURED" and st["tavily"] == "CONFIGURED"


def test_snapshot_reflects_mock_mode_truthfully(_base_settings):
    """MOCK_MODE=true -> the aggregate is MOCK and no cloud provider is ever
    CONNECTED/CONFIGURED. Whether a per-provider cell is NOT_CONFIGURED or MOCK
    depends on whether a key is present in this environment's .env (both are
    honest); the invariant is: never a false live state under mock mode."""
    _base_settings.mock_mode = True
    from app.db.base import session_scope
    from app.support.snapshot import build_snapshot
    with session_scope() as db:
        s = build_snapshot(db, admin=True)
    cp = s["system"]["cloud_providers"]
    assert cp["llm_is_mock"] is True and cp["status"] == "MOCK"
    provs = {p["provider"]: p["status"] for p in cp["providers"]}
    for prov in ("anthropic", "tavily", "google", "elevenlabs"):
        assert provs[prov] in ("NOT_CONFIGURED", "MOCK"), (prov, provs[prov])
        assert provs[prov] not in ("CONNECTED", "CONFIGURED")


def test_ollama_disabled_but_running_reports_degraded_not_connected(_base_settings, monkeypatch):
    _base_settings.ollama_enabled = False
    from app.providers import status as st

    class _FakeOllama:
        def __init__(self, *a, **k):
            pass

        def health(self):
            return {"status": "CONNECTED", "models": ["gemma3:4b"]}

    monkeypatch.setattr("app.providers.ollama_llm.OllamaLLMProvider", _FakeOllama)
    row = next(p for p in st.provider_status(probe=True)["providers"] if p["provider"] == "ollama")
    assert row["status"] == "DEGRADED"
    assert row["service_reachable"] is True and row["model_present"] is True
    assert row["status"] != "CONNECTED"


def test_ollama_enabled_and_running_reports_connected(_base_settings, monkeypatch):
    _base_settings.ollama_enabled = True

    class _FakeOllama:
        def __init__(self, *a, **k):
            pass

        def health(self):
            return {"status": "CONNECTED", "models": ["gemma3:4b"]}

    monkeypatch.setattr("app.providers.ollama_llm.OllamaLLMProvider", _FakeOllama)
    from app.providers import status as st
    row = next(p for p in st.provider_status(probe=True)["providers"] if p["provider"] == "ollama")
    assert row["status"] == "CONNECTED" and row["model_present"] is True


def test_ollama_disabled_and_down_is_not_configured(_base_settings, monkeypatch):
    _base_settings.ollama_enabled = False

    class _DeadOllama:
        def __init__(self, *a, **k):
            pass

        def health(self):
            raise ConnectionError("refused")

    monkeypatch.setattr("app.providers.ollama_llm.OllamaLLMProvider", _DeadOllama)
    from app.providers import status as st
    row = next(p for p in st.provider_status(probe=True)["providers"] if p["provider"] == "ollama")
    assert row["status"] == "NOT_CONFIGURED" and row["service_reachable"] is False


def test_env_var_names_map_to_config_fields():
    from app.config import Settings
    fields = set(Settings.model_fields)
    for env in ("MOCK_MODE", "ANTHROPIC_API_KEY", "TAVILY_API_KEY", "GOOGLE_API_KEY",
                "IMAGE_PROVIDER", "VIDEO_PROVIDER", "GOOGLE_IMAGE_MODEL", "GOOGLE_VIDEO_MODEL",
                "ELEVENLABS_API_KEY", "TTS_PROVIDER", "ELEVENLABS_VOICE_ID", "ELEVENLABS_MODEL",
                "OLLAMA_ENABLED", "OLLAMA_BASE_URL", "OLLAMA_DEFAULT_MODEL"):
        assert env.lower() in fields, env
