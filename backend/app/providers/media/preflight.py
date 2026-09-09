"""Configuration and optional read-only model checks; quota is not guaranteed."""
from app.config import get_settings
from app.providers.errors import ProviderError
from app.providers.media import registry, runtime
from app.providers.media._http import http_json
from urllib.parse import quote


def validate_media_setup(workspace_id=None, video_mode=None, *, verify_remote=False):
    if get_settings().mock_mode:
        return
    with runtime.media_workspace(workspace_id):
        image = registry.get_image_provider()
        registry.get_tts_provider().validate_configuration()
        providers = [(image, "generateContent")]
        if video_mode == "VEO":
            video = registry.get_video_provider()
            if video is None:
                raise ProviderError("Google Veo 공급자와 API 키를 연결하세요", "AUTH_ERROR")
            providers.append((video, "predictLongRunning"))
        if verify_remote:
            for provider, method in providers:
                model = http_json(
                    f"{provider._base}/v1beta/models/{quote(provider._model, safe='')}",
                    headers={"x-goog-api-key": provider._key}, timeout=15, vendor="google")
                if method not in (model.get("supportedGenerationMethods") or []):
                    raise ProviderError(
                        f"Google 모델 {provider._model}에서 {method}를 지원하지 않습니다. 모델 설정을 확인하세요",
                        "AUTH_ERROR")
