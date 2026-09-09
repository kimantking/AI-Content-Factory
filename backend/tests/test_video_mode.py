import pytest

from app.db.base import session_scope
from app.db.models import Campaign
from app.providers.errors import ProviderError
from app.providers.media import preflight


def test_video_mode_survives_reload():
    with session_scope() as db:
        row = Campaign(topic="한국어 영상", platforms=["youtube_shorts"], video_mode="VEO")
        db.add(row)
        db.flush()
        db.expire(row)
        assert row.video_mode == "VEO"


def test_motion_mode_does_not_require_video_provider(_base_settings, monkeypatch):
    _base_settings.mock_mode = False
    monkeypatch.setattr(preflight.registry, "get_image_provider", lambda: object())

    class TTS:
        def validate_configuration(self):
            pass

    monkeypatch.setattr(preflight.registry, "get_tts_provider", TTS)
    monkeypatch.setattr(preflight.registry, "get_video_provider", lambda: None)
    preflight.validate_media_setup(video_mode="IMAGE_MOTION")
    with pytest.raises(ProviderError, match="Veo"):
        preflight.validate_media_setup(video_mode="VEO")


def test_remote_model_capability_checked_before_generation(_base_settings, monkeypatch):
    from types import SimpleNamespace
    _base_settings.mock_mode = False
    image = SimpleNamespace(_base="https://generativelanguage.googleapis.com", _model="image-model", _key="secret")
    monkeypatch.setattr(preflight.registry, "get_image_provider", lambda: image)
    monkeypatch.setattr(preflight.registry, "get_tts_provider", lambda: SimpleNamespace(validate_configuration=lambda: None))
    calls = []

    def request(url, **kwargs):
        calls.append((url, kwargs))
        return {"supportedGenerationMethods": ["generateContent"]}

    monkeypatch.setattr(preflight, "http_json", request)
    preflight.validate_media_setup(video_mode="IMAGE_MOTION", verify_remote=True)
    assert len(calls) == 1
    assert "secret" not in calls[0][0]
    assert calls[0][1]["headers"]["x-goog-api-key"] == "secret"
    monkeypatch.setattr(preflight, "http_json", lambda *args, **kwargs: {"supportedGenerationMethods": ["embedContent"]})
    with pytest.raises(ProviderError, match="지원하지"):
        preflight.validate_media_setup(video_mode="IMAGE_MOTION", verify_remote=True)
