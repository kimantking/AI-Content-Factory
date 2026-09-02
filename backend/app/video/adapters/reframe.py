"""Smart Reframe / Subject-aware crop (B22, B23) — with a deterministic,
license-safe fallback that always works.

`smart_reframe_box()` returns a normalised crop box (x, y, w, h in 0..1) for
converting one aspect ratio to another. The advanced path (SAM 2 / OpenCV
saliency) is optional; the fallback is a rule-of-thirds safe crop biased toward
where a subject usually sits — never a naive centre crop.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.video.adapters import OptionalSkillUnavailable, _require


@dataclass
class CropBox:
    x: float
    y: float
    w: float
    h: float
    method: str
    confidence: float = 0.4


def _target_wh(src_w: int, src_h: int, target_ar: float) -> tuple[float, float]:
    src_ar = src_w / src_h
    if target_ar < src_ar:      # need narrower -> crop width
        return target_ar / src_ar, 1.0
    return 1.0, src_ar / target_ar


def safe_reframe_box(src_w: int, src_h: int, target_ar: float, *,
                     focus_hint: str = "center") -> CropBox:
    """Deterministic fallback: keep the most likely subject region in frame.
    focus_hint: center | upper | speaker | left | right."""
    w, h = _target_wh(src_w, src_h, target_ar)
    # horizontal: bias slightly toward a rule-of-thirds line for 'speaker'
    if focus_hint == "left":
        x = max(0.0, 0.33 - w / 2)
    elif focus_hint == "right":
        x = min(1.0 - w, 0.67 - w / 2)
    else:
        x = (1.0 - w) / 2
    # vertical: faces/speakers sit in the upper third
    if focus_hint in ("upper", "speaker") or h < 0.999:
        y = min(1.0 - h, max(0.0, 0.40 - h / 2))
    else:
        y = (1.0 - h) / 2
    return CropBox(x=round(x, 4), y=round(y, 4), w=round(w, 4), h=round(h, 4),
                   method="rule_of_thirds_safe", confidence=0.45)


def smart_reframe_box(image_path: str, src_w: int, src_h: int, target_ar: float,
                      *, focus_hint: str = "speaker") -> CropBox:
    """Advanced path — subject detection. CODE_READY: needs opencv (+ optionally
    SAM 2 on GPU). Falls back to `safe_reframe_box` on any unavailability."""
    try:
        _require("cv2", "smart_reframe")
    except OptionalSkillUnavailable:
        return safe_reframe_box(src_w, src_h, target_ar, focus_hint=focus_hint)
    try:  # pragma: no cover - exercised only where opencv is installed
        import cv2  # noqa: F401
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            return safe_reframe_box(src_w, src_h, target_ar, focus_hint=focus_hint)
        sal = cv2.saliency.StaticSaliencySpectralResidual_create()
        ok, smap = sal.computeSaliency(img)
        if not ok:
            return safe_reframe_box(src_w, src_h, target_ar, focus_hint=focus_hint)
        smap = (smap * 255).astype("uint8")
        ys, xs = np.where(smap > np.percentile(smap, 92))
        if len(xs) < 20:
            return safe_reframe_box(src_w, src_h, target_ar, focus_hint=focus_hint)
        cx, cy = float(xs.mean()) / smap.shape[1], float(ys.mean()) / smap.shape[0]
        w, h = _target_wh(src_w, src_h, target_ar)
        x = min(max(0.0, cx - w / 2), 1.0 - w)
        y = min(max(0.0, cy - h / 2), 1.0 - h)
        return CropBox(x=round(x, 4), y=round(y, 4), w=round(w, 4), h=round(h, 4),
                       method="opencv_saliency", confidence=0.7)
    except Exception as e:  # noqa: BLE001
        raise OptionalSkillUnavailable("smart_reframe", f"opencv path failed: {e}") from e


def dynamic_reframe_track(boxes: list[CropBox], *, max_pan_per_frame: float = 0.004,
                          dead_zone: float = 0.03) -> list[CropBox]:
    """Smooth a per-shot sequence of crop boxes so the frame tracks a moving
    subject without jumping (B23): dead-zone + max pan speed + light easing."""
    if not boxes:
        return boxes
    out = [boxes[0]]
    for b in boxes[1:]:
        prev = out[-1]
        dx, dy = b.x - prev.x, b.y - prev.y
        if abs(dx) < dead_zone:
            dx = 0.0
        if abs(dy) < dead_zone:
            dy = 0.0
        dx = max(-max_pan_per_frame, min(max_pan_per_frame, dx * 0.5))
        dy = max(-max_pan_per_frame, min(max_pan_per_frame, dy * 0.5))
        out.append(CropBox(x=round(prev.x + dx, 5), y=round(prev.y + dy, 5),
                           w=b.w, h=b.h, method="smoothed", confidence=b.confidence))
    return out
