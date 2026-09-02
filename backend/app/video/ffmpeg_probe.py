"""Real ffmpeg-backed measurement for the Technical QA passes (B39, B50, B53, B55).

These call the ffmpeg binary the project already ships (imageio-ffmpeg). Filters
used — ebur128, signalstats, freezedetect, libvmaf — may or may not be compiled
into a given build; every function degrades to ``{"available": False, ...}``
instead of raising, so QA can record UNKNOWN rather than fail.
"""
from __future__ import annotations

import re
import subprocess

from app.media.ffmpeg import ffmpeg_exe


def _run(args: list[str], timeout: float = 180.0) -> str:
    try:
        p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostdin", *args],
                           capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return (p.stderr or "") + (p.stdout or "")


def loudness(path: str) -> dict:
    """Integrated LUFS + true peak via ebur128."""
    out = _run(["-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"])
    m_i = re.search(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", out)
    m_lra = re.search(r"LRA:\s*(-?\d+(?:\.\d+)?)\s*LU", out)
    m_tp = re.findall(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", out)
    if not m_i:
        return {"available": False}
    return {
        "available": True,
        "integrated_lufs": float(m_i.group(1)),
        "loudness_range_lu": float(m_lra.group(1)) if m_lra else None,
        "true_peak_dbtp": max(float(x) for x in m_tp) if m_tp else None,
    }


def check_loudness(path: str, *, target_lufs: float = -14.0, tol: float = 2.0,
                   tp_ceiling: float = -1.0) -> dict:
    r = loudness(path)
    if not r.get("available"):
        return {"status": "UNKNOWN", "detail": "ebur128 not available in this ffmpeg build"}
    off = r["integrated_lufs"] - target_lufs
    tp = r.get("true_peak_dbtp")
    clip = tp is not None and tp > tp_ceiling
    status = "OK"
    if abs(off) > tol:
        status = "OFF_TARGET"
    if clip:
        status = "TRUE_PEAK_OVER"
    return {"status": status, "integrated_lufs": r["integrated_lufs"],
            "offset_from_target": round(off, 2), "true_peak_dbtp": tp,
            "true_peak_over": clip}


def color_stats(path: str, frames: int = 60) -> dict:
    """Mean brightness / saturation across sampled frames via signalstats."""
    out = _run(["-i", path, "-vf", f"select='not(mod(n\\,{max(1, frames)}))',signalstats,metadata=print",
                "-an", "-f", "null", "-"])
    yavg = [float(x) for x in re.findall(r"lavfi\.signalstats\.YAVG=(-?\d+(?:\.\d+)?)", out)]
    satavg = [float(x) for x in re.findall(r"lavfi\.signalstats\.SATAVG=(-?\d+(?:\.\d+)?)", out)]
    if not yavg:
        return {"available": False}
    import statistics
    return {
        "available": True,
        "brightness_mean": round(statistics.fmean(yavg) / 255.0, 4),
        "brightness_spread": round((max(yavg) - min(yavg)) / 255.0, 4),
        "saturation_mean": round(statistics.fmean(satavg) / 255.0, 4) if satavg else None,
        "n_samples": len(yavg),
    }


def freeze_frames(path: str, noise: float = 0.003, min_dur: float = 0.7) -> list[tuple[float, float]]:
    out = _run(["-i", path, "-vf", f"freezedetect=n={noise}:d={min_dur}",
                "-map", "0:v:0", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"freeze_start:\s*(\d+(?:\.\d+)?)", out)]
    ends = [float(x) for x in re.findall(r"freeze_end:\s*(\d+(?:\.\d+)?)", out)]
    return list(zip(starts, ends))


def av_sync_drift(path: str) -> dict:
    """Rough A/V start-offset check from stream start_time."""
    out = _run(["-i", path])
    v = re.search(r"Stream #\d+:\d+.*Video:.*?start (\-?\d+\.\d+)", out)
    a = re.search(r"Stream #\d+:\d+.*Audio:.*?start (\-?\d+\.\d+)", out)
    if not (v and a):
        return {"available": False}
    drift = abs(float(v.group(1)) - float(a.group(1)))
    return {"available": True, "start_drift_s": round(drift, 4),
            "status": "OK" if drift <= 0.1 else "DRIFT"}


def vmaf(reference: str, distorted: str) -> dict:
    """VMAF (BSD+Patent, built into ffmpeg as libvmaf when compiled). CODE_READY."""
    out = _run(["-i", distorted, "-i", reference,
                "-lavfi", "libvmaf=log_fmt=json", "-f", "null", "-"], timeout=600)
    m = re.search(r'"vmaf"\s*:\s*\{[^}]*"mean"\s*:\s*(\d+(?:\.\d+)?)', out) or \
        re.search(r"VMAF score:\s*(\d+(?:\.\d+)?)", out)
    if not m:
        return {"available": False, "detail": "libvmaf not available in this ffmpeg build"}
    return {"available": True, "vmaf_mean": float(m.group(1))}
