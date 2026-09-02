from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from app.config import get_settings
from app.schemas.media import WordTiming

_PUNCT_PAUSE = {",": 0.18, "،": 0.18, ".": 0.32, "!": 0.32, "?": 0.34, "…": 0.4, ":": 0.2, ";": 0.2}


@runtime_checkable
class AlignmentProvider(Protocol):
    name: str

    def align(self, *, text: str, audio_path: str, total_duration: float) -> list[WordTiming]: ...


def _weight(token: str) -> float:
    """Rough spoken-length weight: syllable/char count + trailing-punctuation pause."""
    core = re.sub(r"[^\w가-힣]", "", token)
    base = max(1, len(core))
    pause = sum(_PUNCT_PAUSE.get(ch, 0.0) for ch in token if not ch.isalnum())
    return base + pause * 3.0


class EstimatorAlignmentProvider:
    """Deterministic proportional alignment. No external model — distributes the
    real audio duration across tokens by weight. This is honest word timing for a
    mock voice, not a guess dressed up as forced alignment."""

    name = "estimator"

    def align(self, *, text: str, audio_path: str, total_duration: float) -> list[WordTiming]:
        tokens = [t for t in re.split(r"\s+", text.strip()) if t]
        if not tokens:
            return []
        weights = [_weight(t) for t in tokens]
        total_w = sum(weights) or 1.0
        out: list[WordTiming] = []
        t = 0.0
        for tok, w in zip(tokens, weights):
            dur = total_duration * (w / total_w)
            out.append(WordTiming(word=tok, start=round(t, 3), end=round(t + dur, 3)))
            t += dur
        out[-1].end = round(total_duration, 3)
        return out


class WhisperXAlignmentProvider:
    """Optional real forced alignment. Deferred (Design Amendment §11): import is
    lazy and absence must not crash the system — the runner falls back to the
    estimator."""

    name = "whisperx"

    def align(self, *, text: str, audio_path: str, total_duration: float) -> list[WordTiming]:
        import whisperx  # noqa: F401  — raises ImportError if not installed

        raise NotImplementedError(
            "WhisperX adapter is scaffolded but not implemented in Phase 1-B"
        )


def get_alignment_provider() -> AlignmentProvider:
    s = get_settings()
    if s.alignment_provider == "whisperx":
        try:
            import whisperx  # noqa: F401

            return WhisperXAlignmentProvider()
        except Exception:  # noqa: BLE001 — not installed / broken → fall back
            return EstimatorAlignmentProvider()
    return EstimatorAlignmentProvider()
