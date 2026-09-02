"""Subtitle Director V2 helpers — caption collision detection + position resolver
(B33, B34).

Deterministic. Given a caption block and the "avoid zones" for a scene (face,
main object, chart, UI, platform safe-area), pick a vertical band that doesn't
collide, and pick which words to emphasise (number / keyword / reveal / emotion)
— only the ones that matter, not every word.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_NUM = re.compile(r"\d[\d,.%]+|\d+")
_EMOTION_WORDS = ("놀랍", "충격", "위험", "기회", "실패", "성공", "손해", "이득")

# normalised vertical bands (y_top, y_bottom) in 0..1
BANDS = {
    "lower_third": (0.72, 0.92),
    "upper_third": (0.08, 0.26),
    "center": (0.42, 0.58),
    "lower_mid": (0.60, 0.76),
}

# where each avoid-zone typically sits vertically for short-form
_ZONE_Y = {
    "face": (0.15, 0.55),
    "speaker": (0.15, 0.55),
    "chart": (0.25, 0.75),
    "ui": (0.0, 0.14),
    "platform_safe_zones": (0.86, 1.0),      # right-side action buttons / bottom bar
    "main_object": (0.30, 0.70),
    "object": (0.30, 0.70),
}


@dataclass
class CaptionPlacement:
    band: str
    y_top: float
    y_bottom: float
    collided_with: list[str]
    emphasis: list[str]


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    return max(0.0, hi - lo)


def resolve_placement(text: str, avoid_zones: list[str], *,
                      preferred: str = "lower_third") -> CaptionPlacement:
    zones = [z for z in (avoid_zones or []) if z in _ZONE_Y]
    order = [preferred] + [b for b in ("lower_third", "lower_mid", "upper_third", "center")
                           if b != preferred]
    best = None
    for band in order:
        span = BANDS[band]
        collides = [z for z in zones if _overlap(span, _ZONE_Y[z]) > 0.03]
        if not collides:
            return CaptionPlacement(band=band, y_top=span[0], y_bottom=span[1],
                                    collided_with=[], emphasis=emphasis_words(text))
        if best is None or len(collides) < len(best[1]):
            best = (band, collides)
    band, collides = best
    return CaptionPlacement(band=band, y_top=BANDS[band][0], y_bottom=BANDS[band][1],
                            collided_with=collides, emphasis=emphasis_words(text))


def emphasis_words(text: str, *, max_words: int = 2) -> list[str]:
    """Only the words worth animating: numbers first, then an emotion word."""
    out: list[str] = []
    for m in _NUM.finditer(text or ""):
        out.append(m.group(0))
        if len(out) >= max_words:
            return out
    for w in re.findall(r"[\w가-힣]+", text or ""):
        if any(e in w for e in _EMOTION_WORDS) and w not in out:
            out.append(w)
            if len(out) >= max_words:
                break
    return out[:max_words]


def caption_load_ok(text: str, duration: float, *, max_cps: float = 17.0) -> tuple[bool, float]:
    """Characters-per-second reading-speed check for a caption block."""
    chars = len(re.sub(r"\s", "", text or ""))
    cps = chars / max(0.4, duration)
    return cps <= max_cps, round(cps, 1)
