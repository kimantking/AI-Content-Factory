from __future__ import annotations

import re
import subprocess
from functools import lru_cache

from app.providers.errors import ProviderError


@lru_cache
def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return "ffmpeg"  # rely on PATH


def run_ffmpeg(args: list[str], *, timeout: float = 240.0) -> str:
    """Run ffmpeg with an ARGUMENT LIST (never a shell string) — no injection surface."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *[str(a) for a in args]]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ProviderError(f"ffmpeg timeout after {timeout}s", error_type="TIMEOUT") from e
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
        raise ProviderError("ffmpeg failed: " + " | ".join(tail), error_type="PROVIDER_ERROR")
    return proc.stderr


_DUR_RE = re.compile(r"Duration:\s+(\d+):(\d+):(\d+\.\d+)")
_VID_RE = re.compile(r"Stream #\d+:\d+.*Video:.*?,\s*(\d+)x(\d+).*?(\d+(?:\.\d+)?)\s*fps", re.S)
_VID_RE2 = re.compile(r"Stream #\d+:\d+.*Video:.*?(\d{2,5})x(\d{2,5})")
_AUD_RE = re.compile(r"Stream #\d+:\d+.*Audio:")


def probe(path: str) -> dict:
    """Media facts via `ffmpeg -i` stderr parsing (this ffmpeg build ships no ffprobe)."""
    try:
        proc = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)],
                              capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as e:
        raise ProviderError("ffprobe(ffmpeg -i) timeout", error_type="TIMEOUT") from e
    text = proc.stderr or ""
    info: dict = {"has_video": "Video:" in text, "has_audio": bool(_AUD_RE.search(text))}
    m = _DUR_RE.search(text)
    if m:
        h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        info["duration"] = round(h * 3600 + mi * 60 + s, 3)
    mv = _VID_RE.search(text) or _VID_RE2.search(text)
    if mv:
        info["width"] = int(mv.group(1))
        info["height"] = int(mv.group(2))
        if mv.lastindex and mv.lastindex >= 3:
            try:
                info["fps"] = float(mv.group(3))
            except (TypeError, ValueError):
                pass
    return info


def detect_black(path: str, min_dur: float = 0.5) -> list[tuple[float, float]]:
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path), "-vf",
         f"blackdetect=d={min_dur}:pic_th=0.98", "-an", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    out = []
    for m in re.finditer(r"black_start:(\d+\.?\d*)\s+black_end:(\d+\.?\d*)", proc.stderr or ""):
        out.append((float(m.group(1)), float(m.group(2))))
    return out


def detect_silence(path: str, noise_db: int = -45, min_dur: float = 0.8) -> list[tuple[float, float]]:
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path), "-af",
         f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    starts = [float(m.group(1)) for m in re.finditer(r"silence_start:\s*(-?\d+\.?\d*)", proc.stderr or "")]
    ends = [float(m.group(1)) for m in re.finditer(r"silence_end:\s*(-?\d+\.?\d*)", proc.stderr or "")]
    return list(zip(starts, ends))
