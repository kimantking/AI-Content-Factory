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
