"""Exercise REAL provider selection with persisted credentials, without paid HTTP."""
import pytest

from app.providers import credentials
from app.providers.errors import ProviderError
from app.providers.media import registry, runtime


def test_worker_reads_saved_key_and_voice_without_settings_mutation(_base_settings, monkeypatch):
    s = _base_settings
    s.mock_mode = False
    s.tts_provider = "elevenlabs"
    s.elevenlabs_api_key = None
    s.tts_api_key = None
    s.elevenlabs_voice_id = ""
    monkeypatch.setattr(registry, "_paid_media_blocked", lambda: False)
    credentials.set_key("elevenlabs", "sk_test_worker_key")
    credentials.set_meta("elevenlabs", {"voice_id": "saved-voice"})
    with runtime.media_workspace(None):
        provider = registry.get_tts_provider()
        provider.validate_configuration()
    assert provider._key == "sk_test_worker_key"
    assert provider._default_voice == "saved-voice"
    assert s.elevenlabs_voice_id == ""


def test_workspace_credentials_do_not_leak(_base_settings):
    credentials.set_key("google", "instance-key")
    credentials.set_key("google", "workspace-a-key", workspace_id="a")
    with runtime.media_workspace("a"):
        assert runtime.key("google") == "workspace-a-key"
    with runtime.media_workspace("b"):
        assert runtime.key("google") == "instance-key"


def test_missing_voice_is_actionable(_base_settings, monkeypatch):
    s = _base_settings
    s.mock_mode = False
    s.tts_provider = "elevenlabs"
    s.elevenlabs_voice_id = ""
    s.elevenlabs_api_key = "sk_test"
    monkeypatch.setattr(registry, "_paid_media_blocked", lambda: False)
    with pytest.raises(ProviderError, match="목소리를 선택"):
        registry.get_tts_provider().validate_configuration()


def test_google_uses_saved_key(_base_settings, monkeypatch):
    s = _base_settings
    s.mock_mode = False
    s.image_provider = "google"
    s.google_api_key = None
    s.image_api_key = None
    monkeypatch.setattr(registry, "_paid_media_blocked", lambda: False)
    credentials.set_key("google", "saved-google-key")
    assert registry.get_image_provider()._key == "saved-google-key"
