from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.providers.media.mock_image import MockImageProvider
from app.providers.media.mock_music import MockMusicProvider
from app.providers.media.mock_stock import MockStockProvider
from app.providers.media.mock_tts import MockTTSProvider
from app.providers.media.storage import LocalStorage
from app.schemas.media import ProviderMode
from app.providers.errors import ProviderError


def _paid_media_blocked() -> bool:
    """GLOBAL_PAID_PROVIDER_PAUSE also stops real paid media providers — the
    pipeline falls back to the mock/deterministic path."""
    try:
        from app.ops.runtime_flags import paid_provider_paused

        return paid_provider_paused()
    except Exception:  # noqa: BLE001
        return False


def get_image_provider():
    s = get_settings()
    if (s.image_provider == "google" and not s.media_provider_is_mock("image")
            and not _paid_media_blocked()):
        from app.providers.media.google_image import GoogleImageProvider

        return GoogleImageProvider()
    if s.mock_mode:
        return MockImageProvider()
    raise ProviderError("실사용 이미지 공급자(Google)와 API 키를 설정하세요", "AUTH_ERROR")


def get_video_provider():
    """Real Google/Veo adapter when configured; otherwise None so the pipeline
    falls back to the Image Motion Engine (unchanged behaviour)."""
    s = get_settings()
    if (s.video_provider == "google" and not s.media_provider_is_mock("video")
            and not _paid_media_blocked()):
        from app.providers.media.google_video import GoogleVideoProvider

        return GoogleVideoProvider()
    if s.mock_mode:
        return None
    raise ProviderError("실사용 영상 공급자(Google/Veo)와 API 키를 설정하세요", "AUTH_ERROR")


def get_tts_provider():
    s = get_settings()
    if (s.tts_provider == "elevenlabs" and not s.media_provider_is_mock("tts")
            and not _paid_media_blocked()):
        from app.providers.media.elevenlabs_tts import ElevenLabsTTSProvider

        return ElevenLabsTTSProvider()
    if s.mock_mode:
        return MockTTSProvider()
    raise ProviderError("실사용 음성 공급자(ElevenLabs), API 키, Voice ID를 설정하세요", "AUTH_ERROR")


def get_stock_provider():
    return MockStockProvider() if get_settings().mock_mode else None


def get_music_provider():
    provider = MockMusicProvider()
    if not get_settings().mock_mode:
        # This adapter really synthesizes an original local WAV; in live mode it
        # is a zero-cost local generator, not simulated third-party stock music.
        provider.name = "local-generated-music"
        provider.mode = ProviderMode.REAL
    return provider


@lru_cache
def get_storage() -> LocalStorage:
    return LocalStorage()


def media_provider_status() -> list[dict]:
    s = get_settings()
    out = []
    for kind in ("image", "video", "tts", "stock", "music"):
        getter = globals()[f"get_{kind}_provider"]
        prov = getter()
        if prov is None:
            out.append({"kind": kind, "provider": None, "mode": ProviderMode.DISABLED.value})
        else:
            out.append({
                "kind": kind,
                "provider": getattr(prov, "name", "unknown"),
                "mode": getattr(prov, "mode", ProviderMode.MOCK).value,
                "configured": getattr(s, f"{kind}_provider", "mock"),
            })
    return out
