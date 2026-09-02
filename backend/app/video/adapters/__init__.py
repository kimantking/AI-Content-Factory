"""Optional GPU/model-backed video skills (B20-B25, B33-B35, B64-B66).

Every adapter here is CODE_READY: the interface + wiring exist, but the heavy
dependency and/or GPU is not assumed. Each raises `OptionalSkillUnavailable` when
it cannot run — it NEVER returns a fabricated result. The router points callers to
a deterministic fallback in that case.

License notes (verified 2026-08-31, code vs model weights separately):
  - SAM 2 .............. Apache-2.0 code + weights  -> commercial OK
  - Depth-Anything-V2 .. S/B/L weights Apache-2.0 (OK); Giant CC-BY-NC-4.0 (NO)
  - CoTracker ......... code + weights historically CC-BY-NC-4.0 -> REFERENCE_ONLY
  - OpenCV ............ Apache-2.0 (>=4.5)          -> commercial OK  (tracking fallback)
  - faster-whisper .... MIT ; WhisperX .. BSD-2     -> commercial OK
  - pyannote.audio .... code MIT, models gated-but-free-commercial; prefer
                        NeMo / SpeechBrain (Apache-2.0, ungated) for diarization
  - Real-ESRGAN ....... BSD-3 code; some pretrained weights carry dataset terms
  - RIFE ............. MIT code; some model weights non-commercial -> verify
"""
from __future__ import annotations


class OptionalSkillUnavailable(RuntimeError):
    """Raised when an optional GPU/model skill cannot run (missing dep / GPU /
    a non-commercial weight license). Callers must fall back, never fake."""

    def __init__(self, skill: str, reason: str):
        super().__init__(f"{skill}: {reason}")
        self.skill = skill
        self.reason = reason


def _require(mod: str, skill: str) -> None:
    import importlib.util

    if importlib.util.find_spec(mod) is None:
        raise OptionalSkillUnavailable(skill, f"python package '{mod}' not installed (CODE_READY)")
