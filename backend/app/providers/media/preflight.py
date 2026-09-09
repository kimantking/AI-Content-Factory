"""Configuration checks only: no paid request and no promise of quota availability."""
from app.config import get_settings
from app.providers.errors import ProviderError
from app.providers.media import registry, runtime


def validate_media_setup(workspace_id=None, video_mode=None):
    if get_settings().mock_mode:
        return
    with runtime.media_workspace(workspace_id):
        registry.get_image_provider()
        registry.get_tts_provider().validate_configuration()
        if video_mode == "VEO" and registry.get_video_provider() is None:
            raise ProviderError("Google Veo 공급자와 API 키를 연결하세요", "AUTH_ERROR")
