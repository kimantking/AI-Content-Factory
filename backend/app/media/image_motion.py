from __future__ import annotations

from app.media.ffmpeg import run_ffmpeg

# Image Motion Engine — turns a still into a moving clip so no scene ever sits
# frozen. Used as the universal fallback when no real VideoProvider is available.

MOTIONS = {
    "SLOW_ZOOM_IN", "SLOW_ZOOM_OUT", "PAN_LEFT", "PAN_RIGHT",
    "PAN_UP", "PAN_DOWN", "KEN_BURNS",
}

# Cinematic motions (Video Studio Upgrade) are delegated to app.video.motion,
# which knows the parallax/dolly/focus-pull simulations. Legacy motions keep the
# original local builder so nothing about the existing fallback path changes.
_CINEMATIC = {
    "DEPTH_PARALLAX_SIM", "DOLLY_IN_SIM", "DOLLY_OUT_SIM", "SUBJECT_PUSH",
    "BACKGROUND_DRIFT", "SLOW_ORBIT_SIM", "FOCUS_PULL_SIM",
}


def _zoompan_expr(motion: str, frames: int, w: int, h: int) -> str:
    if motion and motion.upper() in _CINEMATIC:
        from app.video.motion import zoompan_expr

        return zoompan_expr(motion, frames, w, h, fps=30)
    d = max(1, frames)
    m = motion.upper() if motion else "SLOW_ZOOM_IN"
    if m == "SLOW_ZOOM_OUT":
        z = f"'if(lte(on,1),1.12,max(1.001,zoom-0.0009))'"
        x, y = "'iw/2-(iw/zoom/2)'", "'ih/2-(ih/zoom/2)'"
    elif m == "PAN_LEFT":
        z, x, y = "1.12", f"'(iw-iw/zoom)*(1-on/{d})'", "'ih/2-(ih/zoom/2)'"
    elif m == "PAN_RIGHT":
        z, x, y = "1.12", f"'(iw-iw/zoom)*(on/{d})'", "'ih/2-(ih/zoom/2)'"
    elif m == "PAN_UP":
        z, x, y = "1.12", "'iw/2-(iw/zoom/2)'", f"'(ih-ih/zoom)*(1-on/{d})'"
    elif m == "PAN_DOWN":
        z, x, y = "1.12", "'iw/2-(iw/zoom/2)'", f"'(ih-ih/zoom)*(on/{d})'"
    elif m == "KEN_BURNS":
        z = "'min(zoom+0.0009,1.15)'"
        x, y = f"'(iw-iw/zoom)*(on/{d})'", "'ih/2-(ih/zoom/2)'"
    else:  # SLOW_ZOOM_IN
        z = "'min(zoom+0.0009,1.12)'"
        x, y = "'iw/2-(iw/zoom/2)'", "'ih/2-(ih/zoom/2)'"
    return (
        f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,"
        f"crop={w*2}:{h*2},"
        f"zoompan=z={z}:d={d}:x={x}:y={y}:s={w}x{h}:fps=30,"
        f"trim=duration={d/30.0}"
    )


def render_scene_clip(image_path: str, out_path: str, *, duration: float,
                      width: int, height: int, fps: int = 30, motion: str = "SLOW_ZOOM_IN") -> str:
    frames = max(1, round(duration * 30))
    vf = _zoompan_expr(motion, frames, width, height)
    run_ffmpeg([
        "-loop", "1", "-t", f"{duration:.3f}", "-i", image_path,
        "-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
        "-vf", vf,
        "-r", str(fps),
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart",
        out_path,
    ])
    return out_path
