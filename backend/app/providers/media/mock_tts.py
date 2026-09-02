from __future__ import annotations

import math
import struct
import wave

from app.providers.faults import faults
from app.providers.media.base import MediaResult
from app.schemas.media import ProviderMode

_SR = 24000


def estimate_seconds(text: str, speed: float = 1.0) -> float:
    """~3.4 Korean syllables/sec baseline; clamp to a sane range."""
    chars = max(1, len([c for c in text if not c.isspace()]))
    secs = chars / (3.4 * max(0.5, speed))
    return round(min(max(secs, 1.2), 30.0), 3)


class MockTTSProvider:
    """Offline TTS. Emits a real WAV whose DURATION matches the estimate, so the
    rest of the media pipeline (timing, subtitles, render) is exercised for real.
    Audio content is a near-silent low tone (clearly not a real voice)."""

    name = "mock-tts"
    mode = ProviderMode.MOCK

    def synthesize(self, *, text: str, voice_id: str, language: str, speed: float,
                   emotion: str, style: str, out_path: str) -> MediaResult:
        faults.maybe_raise("tts", "media")
        dur = estimate_seconds(text, speed)
        n = int(dur * _SR)
        with wave.open(out_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(_SR)
            frames = bytearray()
            for i in range(n):
                # -40 dBFS 140 Hz hum with a slow envelope; placeholder, not speech
                env = 0.5 - 0.5 * math.cos(2 * math.pi * min(i / n, 1.0))
                val = int(320 * env * math.sin(2 * math.pi * 140 * (i / _SR)))
                frames += struct.pack("<h", val)
            w.writeframes(bytes(frames))
        return MediaResult(
            path=out_path, mime_type="audio/wav", provider=self.name,
            provider_mode=self.mode, duration=dur, cost=0.0,
            meta={"voice_id": voice_id, "language": language, "speed": speed,
                  "emotion": emotion, "style": style, "chars": len(text)},
        )
