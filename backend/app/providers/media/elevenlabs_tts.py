"""ElevenLabs voice adapter — stdlib HTTP, no new dependency.

Implements the existing `TTSProvider` protocol. Requests raw 24 kHz PCM and wraps
it in a WAV container so the rest of the media pipeline (timing / subtitles /
render) works exactly as with the mock. Uses the `/with-timestamps` endpoint so
the returned `duration` is accurate (last character end-time), not estimated.

Voice id + model come from config (`settings.elevenlabs_voice_id` /
`elevenlabs_model`) — no invented default voice. Voice cloning is NOT done here.
No paid synthesis is performed by any test.
"""
from __future__ import annotations

import base64
import wave

from app.config import get_settings
from app.providers.media import runtime
from app.providers.media._http import http_json, provider_error
from app.providers.media.base import MediaResult
from app.schemas.media import ProviderMode

_SR = 24000  # pcm_24000


class ElevenLabsTTSProvider:
    name = "elevenlabs"
    mode = ProviderMode.REAL

    def __init__(self) -> None:
        s = get_settings()
        self._key = runtime.key("elevenlabs", s.tts_api_key)
        self._base = s.elevenlabs_api_base.rstrip("/")
        self._model = s.elevenlabs_model
        self._default_voice = runtime.voice()
        self._timeout = s.elevenlabs_timeout_seconds
        if not self._key:
            raise provider_error("elevenlabs", "NOT_CONFIGURED", "ELEVENLABS_API_KEY is not set")

    def validate_configuration(self):
        if not self._default_voice:
            raise provider_error(
                "elevenlabs", "NOT_CONFIGURED",
                "AI 연결 설정에서 목소리를 선택하거나 ELEVENLABS_VOICE_ID를 설정하세요",
            )

    def synthesize(self, *, text: str, voice_id: str, language: str, speed: float,
                   emotion: str, style: str, out_path: str) -> MediaResult:
        voice = self._default_voice or voice_id
        if not voice:
            raise provider_error("elevenlabs", "NOT_CONFIGURED",
                                 "ELEVENLABS_VOICE_ID is not set and no voice_id was provided")
        url = (f"{self._base}/v1/text-to-speech/{voice}/with-timestamps"
               f"?output_format=pcm_24000")
        body = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75,
                               "style": 0.0, "use_speaker_boost": True},
        }
        data = http_json(url, method="POST",
                         headers={"xi-api-key": self._key, "Accept": "application/json"},
                         body=body, timeout=self._timeout, vendor="elevenlabs")
        b64 = data.get("audio_base64")
        if not b64:
            raise provider_error("elevenlabs", "PROVIDER_ERROR", "no audio in response")
        try:
            pcm = base64.b64decode(b64, validate=True)
            if not pcm or len(pcm) % 2:
                raise ValueError("invalid PCM frame size")
        except (ValueError, TypeError) as exc:
            raise provider_error("elevenlabs", "PROVIDER_ERROR", "생성된 음성 데이터가 손상되었습니다") from exc
        with wave.open(out_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(_SR)
            w.writeframes(pcm)

        # Actual WAV duration includes trailing audio after the last character.
        duration = round(len(pcm) / (2 * _SR), 3)

        return MediaResult(
            path=out_path, mime_type="audio/wav", provider=self.name, provider_mode=self.mode,
            duration=duration, cost=0.0,   # ElevenLabs pricing is UNKNOWN until verified
            meta={"model": self._model, "voice_id": voice, "chars": len(text),
                  "cost_state": "UNKNOWN", "language": language},
        )

    # ---- read-only connection test (no synthesis, no cost) ---- #
    def health(self) -> dict:
        try:
            data = http_json(f"{self._base}/v1/voices",
                             headers={"xi-api-key": self._key}, timeout=self._timeout,
                             vendor="elevenlabs")
            voices = data.get("voices") or []
            has = any((v.get("voice_id") == (self._default_voice or "")) for v in voices)
            return {"status": "CONNECTED", "voices": len(voices),
                    "configured_voice_present": has if self._default_voice else None,
                    "model": self._model}
        except Exception as e:  # noqa: BLE001
            return {"status": "ERROR",
                    "provider_code": getattr(e, "provider_code", "ELEVENLABS_PROVIDER_ERROR"),
                    "detail": str(e)[:200]}
