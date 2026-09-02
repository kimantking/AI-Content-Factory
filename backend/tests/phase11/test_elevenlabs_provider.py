"""Phase 11 — ElevenLabs voice adapter. Mocked HTTP only — NO paid synthesis.
Config resolution, registry selection, happy path (WAV written + accurate
duration from alignment), missing voice, error normalisation, health, cost
= UNKNOWN."""
from __future__ import annotations

import base64
import wave

import pytest

from app.providers.errors import ProviderError

pytestmark = [pytest.mark.phase11]

_PCM = b"\x00\x01" * 24000            # 1 s of 24 kHz mono 16-bit


@pytest.fixture
def eleven_on(_base_settings):
    _base_settings.mock_mode = False
    _base_settings.elevenlabs_api_key = "test-11-key"
    _base_settings.tts_provider = "elevenlabs"
    _base_settings.elevenlabs_voice_id = "voice-abc"
    return _base_settings


def test_registry_selects_elevenlabs_only_when_configured(_base_settings):
    from app.providers.media import registry
    assert type(registry.get_tts_provider()).__name__ == "MockTTSProvider"

    _base_settings.mock_mode = False
    _base_settings.elevenlabs_api_key = "k"
    _base_settings.tts_provider = "elevenlabs"
    assert type(registry.get_tts_provider()).__name__ == "ElevenLabsTTSProvider"

    _base_settings.tts_provider = "mock"
    assert type(registry.get_tts_provider()).__name__ == "MockTTSProvider"


def test_elevenlabs_synthesize_writes_wav_with_alignment_duration(eleven_on, monkeypatch, tmp_path):
    from app.providers.media import elevenlabs_tts as el
    seen = {}

    def fake(url, **kw):
        seen["url"] = url
        seen["headers"] = kw.get("headers")
        seen["body"] = kw.get("body")
        return {"audio_base64": base64.b64encode(_PCM).decode(),
                "alignment": {"character_end_times_seconds": [0.2, 0.5, 0.97]}}

    monkeypatch.setattr(el, "http_json", fake)
    out = str(tmp_path / "scene_001.wav")
    res = el.ElevenLabsTTSProvider().synthesize(
        text="안녕하세요, 테스트입니다.", voice_id="ignored-because-config-wins",
        language="ko", speed=1.0, emotion="neutral", style="NARRATION", out_path=out)

    assert res.provider == "elevenlabs" and res.provider_mode.value == "REAL"
    assert res.mime_type == "audio/wav" and res.duration == 0.97
    assert res.cost == 0.0 and res.meta["cost_state"] == "UNKNOWN"
    assert res.meta["voice_id"] == "voice-abc"          # config voice wins
    assert seen["headers"]["xi-api-key"] == "test-11-key"
    assert seen["body"]["model_id"] == "eleven_multilingual_v2"
    with wave.open(out, "rb") as w:
        assert w.getframerate() == 24000 and w.getnchannels() == 1


def test_elevenlabs_missing_key_and_voice(_base_settings):
    _base_settings.elevenlabs_api_key = None
    _base_settings.tts_api_key = None
    from app.providers.media.elevenlabs_tts import ElevenLabsTTSProvider
    with pytest.raises(ProviderError) as ei:
        ElevenLabsTTSProvider()
    assert getattr(ei.value, "provider_code", "") == "ELEVENLABS_NOT_CONFIGURED"

    _base_settings.mock_mode = False
    _base_settings.elevenlabs_api_key = "k"
    _base_settings.elevenlabs_voice_id = ""             # no invented default
    with pytest.raises(ProviderError) as ei2:
        ElevenLabsTTSProvider().synthesize(text="x", voice_id="", language="ko", speed=1.0,
                                           emotion="", style="", out_path="/tmp/x.wav")
    assert getattr(ei2.value, "provider_code", "") == "ELEVENLABS_NOT_CONFIGURED"


@pytest.mark.parametrize("status,code,etype", [
    (401, "ELEVENLABS_AUTH_FAILED", "AUTH_ERROR"),
    (429, "ELEVENLABS_RATE_LIMITED", "RATE_LIMIT"),
    (500, "ELEVENLABS_PROVIDER_ERROR", "PROVIDER_ERROR"),
])
def test_elevenlabs_http_error_is_normalised(eleven_on, monkeypatch, tmp_path, status, code, etype):
    import io
    import urllib.error
    from app.providers.media import _http, elevenlabs_tts as el

    monkeypatch.setattr(_http.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            urllib.error.HTTPError("u", status, "e", {}, io.BytesIO(b"{}"))))
    with pytest.raises(ProviderError) as ei:
        el.ElevenLabsTTSProvider().synthesize(text="x", voice_id="v", language="ko", speed=1.0,
                                              emotion="", style="", out_path=str(tmp_path / "e.wav"))
    assert getattr(ei.value, "provider_code", "") == code and ei.value.error_type == etype


def test_elevenlabs_health_is_read_only(eleven_on, monkeypatch):
    from app.providers.media import elevenlabs_tts as el
    calls = []
    monkeypatch.setattr(el, "http_json", lambda url, **kw: calls.append(url) or
                        {"voices": [{"voice_id": "voice-abc"}, {"voice_id": "z"}]})
    h = el.ElevenLabsTTSProvider().health()
    assert h["status"] == "CONNECTED" and h["voices"] == 2
    assert h["configured_voice_present"] is True
    assert all("text-to-speech" not in u for u in calls)   # never a synthesis call
