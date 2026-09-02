from __future__ import annotations

import math
import struct
import wave

from app.providers.faults import faults
from app.providers.media.base import MediaResult
from app.schemas.media import ProviderMode

_SR = 24000


class MockMusicProvider:
    """Offline BGM. Emits a real, quiet WAV of the requested length with explicit
    licence metadata (source=generated, commercial_use_allowed=True)."""

    name = "mock-music"
    mode = ProviderMode.MOCK

    def get_track(self, *, mood: str, duration: float, out_path: str) -> MediaResult:
        faults.maybe_raise("music", "media")
        dur = max(1.0, float(duration))
        n = int(dur * _SR)
        root = {"UPBEAT": 196.0, "AMBIENT": 110.0}.get(mood.upper(), 146.83)
        with wave.open(out_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(_SR)
            frames = bytearray()
            for i in range(n):
                t = i / _SR
                val = int(180 * (math.sin(2 * math.pi * root * t)
                                 + 0.5 * math.sin(2 * math.pi * root * 1.5 * t)))
                frames += struct.pack("<h", max(-32768, min(32767, val)))
            w.writeframes(bytes(frames))
        return MediaResult(
            path=out_path, mime_type="audio/wav", provider=self.name,
            provider_mode=self.mode, duration=dur, cost=0.0,
            meta={
                "mood": mood, "source": "generated",
                "license_type": "generated-placeholder",
                "commercial_use_allowed": True, "attribution": None,
            },
        )
