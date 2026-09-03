"""Cinematic Image Motion (B25, B26): FFmpeg filter builders for richer still→motion.

No depth model is used, so parallax / dolly / focus-pull are honestly labelled
`*_SIM` (simulated). Each builder returns an FFmpeg `-vf` string that the existing
renderer path can use; they are deterministic and shell-safe (argument lists are
assembled by the caller). Overdone fake camera moves are explicitly avoided —
rates are gentle.
"""
from __future__ import annotations

_FPS = 30


def _base_scale(w: int, h: int, up: float = 2.0) -> str:
    W, H = int(w * up), int(h * up)
    return (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H}")


def zoompan_expr(motion: str, frames: int, w: int, h: int, *, fps: int = _FPS) -> str:
    """Return a full -vf filter string for `motion`. Falls back to a slow zoom."""
    d = max(1, frames)
    m = (motion or "KEN_BURNS").upper()
    pre = _base_scale(w, h)

    if m in ("DOLLY_IN_SIM", "SUBJECT_PUSH"):
        # accelerating push toward centre — subtle, capped
        z = "'min(zoom+0.0016,1.20)'"
        x, y = "'iw/2-(iw/zoom/2)'", "'ih/2-(ih/zoom/2)'"
    elif m == "DOLLY_OUT_SIM":
        z = "'if(lte(on,1),1.20,max(1.001,zoom-0.0013))'"
        x, y = "'iw/2-(iw/zoom/2)'", "'ih/2-(ih/zoom/2)'"
    elif m == "DEPTH_PARALLAX_SIM":
        # simulate parallax: hold a mild zoom while drifting the crop diagonally,
        # so foreground/background appear to shift at different apparent rates
        z = "1.14"
        x, y = f"'(iw-iw/zoom)*(0.5+0.35*sin(on/{d}*3.14159))'", \
               f"'(ih-ih/zoom)*(0.5-0.25*cos(on/{d}*3.14159))'"
    elif m == "BACKGROUND_DRIFT":
        z = "1.10"
        x, y = f"'(iw-iw/zoom)*(on/{d})'", "'ih/2-(ih/zoom/2)'"
    elif m == "SLOW_ORBIT_SIM":
        z = "1.16"
        x = f"'(iw-iw/zoom)*(0.5+0.4*sin(on/{d}*2*3.14159))'"
        y = f"'(ih-ih/zoom)*(0.5+0.15*cos(on/{d}*2*3.14159))'"
    elif m == "FOCUS_PULL_SIM":
        # no real DOF: emulate with a brief soft->sharp via a boxblur ramp appended below
        z = "'min(zoom+0.0006,1.10)'"
        x, y = "'iw/2-(iw/zoom/2)'", "'ih/2-(ih/zoom/2)'"
    elif m == "KEN_BURNS":
        z = "'min(zoom+0.0011,1.16)'"
        x, y = f"'(iw-iw/zoom)*(on/{d})'", "'ih/2-(ih/zoom/2)'"
    elif m == "SLOW_ZOOM_OUT":
        z = "'if(lte(on,1),1.14,max(1.001,zoom-0.0010))'"
        x, y = "'iw/2-(iw/zoom/2)'", "'ih/2-(ih/zoom/2)'"
    elif m == "PAN_LEFT":
        z, x, y = "1.12", f"'(iw-iw/zoom)*(1-on/{d})'", "'ih/2-(ih/zoom/2)'"
    elif m == "PAN_RIGHT":
        z, x, y = "1.12", f"'(iw-iw/zoom)*(on/{d})'", "'ih/2-(ih/zoom/2)'"
    elif m == "PAN_UP":
        z, x, y = "1.12", "'iw/2-(iw/zoom/2)'", f"'(ih-ih/zoom)*(1-on/{d})'"
    elif m == "PAN_DOWN":
        z, x, y = "1.12", "'iw/2-(iw/zoom/2)'", f"'(ih-ih/zoom)*(on/{d})'"
    else:  # SLOW_ZOOM_IN default
        z = "'min(zoom+0.0009,1.12)'"
        x, y = "'iw/2-(iw/zoom/2)'", "'ih/2-(ih/zoom/2)'"

    vf = (f"{pre},zoompan=z={z}:d={d}:x={x}:y={y}:s={w}x{h}:fps={fps},"
          f"trim=duration={d/fps:.3f}")
    if m == "FOCUS_PULL_SIM":
        # brief blur that resolves over the first ~35% of the clip
        vf += f",boxblur=luma_radius='max(0,4-8*t/{max(0.1, d/fps*0.35):.3f})':luma_power=1:enable='lte(t,{d/fps*0.4:.3f})'"
    return vf


def is_cinematic(motion: str) -> bool:
    return (motion or "").upper() in (
        "DEPTH_PARALLAX_SIM", "DOLLY_IN_SIM", "DOLLY_OUT_SIM", "SUBJECT_PUSH",
        "BACKGROUND_DRIFT", "SLOW_ORBIT_SIM", "FOCUS_PULL_SIM",
    )
