from __future__ import annotations

import json
import re
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

BRANDS_DIR = Path(__file__).resolve().parents[2] / "brands"
SAMPLES_DIRNAME = "writing_samples"


@dataclass
class VoiceProfile:
    """Per-brand writing voice (Design Amendment §5). Not a generic 'human style'."""

    brand: str = "default"
    formality: float = 0.4                 # 0 casual .. 1 formal
    humor: float = 0.2
    directness: float = 0.7
    energy: float = 0.6
    question_frequency: float = 0.15       # share of sentences that are questions
    slang_level: float = 0.1
    technical_level: float = 0.4
    emotion_level: float = 0.4
    storytelling_style: str = "concrete-example-first"
    pause_style: str = "natural-breath"
    sentence_length_distribution: list[int] = field(
        default_factory=lambda: [4, 7, 12, 6, 18, 5, 9]
    )
    favorite_expressions: list[str] = field(default_factory=list)
    forbidden_expressions: list[str] = field(
        default_factory=lambda: [
            "안녕하세요 여러분",
            "오늘은 ~에 대해 알아보겠습니다",
            "지금부터 자세히 살펴보겠습니다",
            "결론적으로",
            "여러분은 어떻게 생각하시나요?",
        ]
    )

    def to_dict(self) -> dict:
        return asdict(self)


def _default_profile(brand: str) -> VoiceProfile:
    return VoiceProfile(brand=brand)


def load_voice_profile(brand: str = "default") -> VoiceProfile:
    """Load brands/<brand>/voice_profile.json, else derive from writing_samples/,
    else fall back to a sane default. Never raises."""
    base = _default_profile(brand)
    bdir = BRANDS_DIR / brand
    pfile = bdir / "voice_profile.json"
    if pfile.exists():
        try:
            data = json.loads(pfile.read_text(encoding="utf-8"))
            merged = {**base.to_dict(), **data, "brand": brand}
            return VoiceProfile(**{k: merged[k] for k in base.to_dict()})
        except (ValueError, TypeError):
            return base

    samples = _read_samples(bdir / SAMPLES_DIRNAME) or _read_samples(BRANDS_DIR.parent / SAMPLES_DIRNAME)
    if samples:
        return analyze_samples(samples, brand=brand)
    return base


def _read_samples(d: Path) -> list[str]:
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.txt")) + sorted(d.glob("*.md")):
        try:
            out.append(f.read_text(encoding="utf-8"))
        except OSError:
            continue
    return out


_SENT_SPLIT = re.compile(r"(?<=[.!?。…])\s+|\n+")


def analyze_samples(samples: list[str], *, brand: str = "default") -> VoiceProfile:
    """Extract rhythm / structure features from user-provided writing (Amendment §6).
    Heuristic only — the model never copies sample sentences verbatim."""
    text = "\n".join(samples)
    sents = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    lens = [len(s.split()) for s in sents] or [8]
    q = sum(1 for s in sents if s.rstrip().endswith(("?", "?")))
    profile = _default_profile(brand)
    profile.sentence_length_distribution = lens[:40]
    profile.question_frequency = round(q / max(1, len(sents)), 3)
    # crude formality proxy: long sentences + few exclamations => more formal
    mean_len = statistics.fmean(lens)
    excl = sum(s.count("!") for s in sents)
    profile.formality = round(min(1.0, max(0.1, mean_len / 25.0 - excl * 0.02)), 2)
    profile.energy = round(min(1.0, 0.4 + excl / max(1, len(sents))), 2)
    return profile
