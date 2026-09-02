"""Color Director (B46, B47, B48): consistency analysis across mixed sources +
a gentle, non-destructive match plan + brand colour language.

Planning + light Pillow-based analysis only (no OpenCV dependency). Real per-frame
stats come from `app.video.ffmpeg_probe.color_stats()` on rendered clips. Matching
is always applied as a *new* asset, never in place (B47/B59).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ColorStats:
    ref: str
    brightness: float          # 0..1 (mean luma)
    contrast: float            # 0..1 (luma stdev, normalised)
    saturation: float          # 0..1
    temperature: float         # -1 cool .. +1 warm (R-B balance)
    source_kind: str = "unknown"


@dataclass
class ColorMatchPlan:
    per_ref: dict[str, dict[str, float]] = field(default_factory=dict)  # ref -> gentle adjustments
    reference_brightness: float = 0.5
    reference_temperature: float = 0.0
    max_adjust: float = 0.12
    notes: list[str] = field(default_factory=list)


def stats_from_pillow(path: str, ref: str, source_kind: str = "unknown") -> ColorStats | None:
    try:
        from PIL import Image, ImageStat
    except Exception:  # noqa: BLE001
        return None
    try:
        im = Image.open(path).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    im.thumbnail((160, 160))
    st = ImageStat.Stat(im)
    r, g, b = st.mean
    luma = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    rr, gg, bb = st.stddev
    contrast = min(1.0, ((0.299 * rr + 0.587 * gg + 0.114 * bb) / 255.0) / 0.35)
    mx = max(r, g, b) or 1.0
    mn = min(r, g, b)
    sat = (mx - mn) / mx
    temp = max(-1.0, min(1.0, (r - b) / 255.0 * 2.5))
    return ColorStats(ref=ref, brightness=round(luma, 3), contrast=round(contrast, 3),
                      saturation=round(sat, 3), temperature=round(temp, 3),
                      source_kind=source_kind)


def build_match_plan(stats: list[ColorStats], *, max_adjust: float = 0.12) -> ColorMatchPlan:
    """Nudge every clip toward the median look, capped so nothing is graded hard."""
    if not stats:
        return ColorMatchPlan()
    import statistics

    ref_b = statistics.median(s.brightness for s in stats)
    ref_t = statistics.median(s.temperature for s in stats)
    ref_s = statistics.median(s.saturation for s in stats)
    plan = ColorMatchPlan(reference_brightness=round(ref_b, 3),
                          reference_temperature=round(ref_t, 3), max_adjust=max_adjust)
    for s in stats:
        adj = {
            "brightness_delta": round(_cap(ref_b - s.brightness, max_adjust), 3),
            "temperature_delta": round(_cap(ref_t - s.temperature, max_adjust * 1.5), 3),
            "saturation_delta": round(_cap(ref_s - s.saturation, max_adjust), 3),
        }
        if any(abs(v) > 0.005 for v in adj.values()):
            plan.per_ref[s.ref] = adj
    spread = max(s.brightness for s in stats) - min(s.brightness for s in stats)
    if spread > 0.35:
        plan.notes.append(f"brightness spread {spread:.2f} across sources — matching recommended")
    warm = [s for s in stats if s.temperature > 0.3]
    cool = [s for s in stats if s.temperature < -0.3]
    if warm and cool:
        plan.notes.append("mixed warm/cool sources — temperature match recommended")
    return plan


def _cap(x: float, lim: float) -> float:
    return max(-lim, min(lim, x))


@dataclass
class BrandColorLanguage:
    primary: list[str] = field(default_factory=lambda: ["#0F172A", "#F8FAFC"])
    accent: list[str] = field(default_factory=lambda: ["#43D1FF"])
    background_preference: str = "dark-gradient"
    contrast_style: str = "high"
    graphic_style: str = "clean-flat"

    def to_dict(self) -> dict:
        return {"primary": self.primary, "accent": self.accent,
                "background_preference": self.background_preference,
                "contrast_style": self.contrast_style, "graphic_style": self.graphic_style}


def load_brand_colors(brand: str = "default") -> BrandColorLanguage:
    import json
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "brands" / brand / "color_language.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            base = BrandColorLanguage()
            return BrandColorLanguage(
                primary=d.get("primary", base.primary),
                accent=d.get("accent", base.accent),
                background_preference=d.get("background_preference", base.background_preference),
                contrast_style=d.get("contrast_style", base.contrast_style),
                graphic_style=d.get("graphic_style", base.graphic_style),
            )
        except (ValueError, TypeError):
            pass
    return BrandColorLanguage()
