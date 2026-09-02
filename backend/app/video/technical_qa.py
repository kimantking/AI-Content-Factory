"""Technical QA V2 (B48, B52) — multi-pass check on a rendered file, using the
bundled ffmpeg via `app.video.ffmpeg_probe` and the existing `app.media.media_qa`.

Each pass returns OK / WARN / FAIL / UNKNOWN. UNKNOWN means the ffmpeg build lacks
that filter — the pipeline is not failed for it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.media.ffmpeg import probe
from app.video import ffmpeg_probe as vp


@dataclass
class TechQAReport:
    passes: dict[str, dict] = field(default_factory=dict)
    verdict: str = "OK"          # OK | WARN | FAIL
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict != "FAIL"


def _v(status: str, **extra) -> dict:
    return {"status": status, **extra}


def run(path: str, *, expect_w: int, expect_h: int, expect_fps: int,
        expect_duration: float, loudness_target_lufs: float = -14.0,
        reference_path: str | None = None) -> TechQAReport:
    r = TechQAReport()
    if not path or not os.path.isfile(path) or os.path.getsize(path) < 1024:
        r.passes["1_file_integrity"] = _v("FAIL", detail="missing or empty")
        r.verdict = "FAIL"
        return r
    r.passes["1_file_integrity"] = _v("OK", bytes=os.path.getsize(path))

    info = probe(path)
    w, h, fps, dur = info.get("width"), info.get("height"), info.get("fps", expect_fps), info.get("duration", 0.0)
    vp2 = "OK"
    detail = {}
    if not info.get("has_video"):
        vp2, detail = "FAIL", {"reason": "no video stream"}
    elif (w, h) != (expect_w, expect_h):
        vp2, detail = "FAIL", {"reason": f"resolution {w}x{h} != {expect_w}x{expect_h}"}
    elif abs(fps - expect_fps) > 2:
        vp2, detail = "WARN", {"reason": f"fps {fps} != {expect_fps}"}
    elif abs(dur - expect_duration) > max(1.5, expect_duration * 0.25):
        vp2, detail = "WARN", {"reason": f"duration {dur} vs {expect_duration}"}
    r.passes["2_video_technical"] = _v(vp2, width=w, height=h, fps=fps, duration=dur, **detail)

    loud = vp.check_loudness(path, target_lufs=loudness_target_lufs)
    r.passes["3_audio_loudness"] = loud
    r.passes["3b_audio_stream"] = _v("OK" if info.get("has_audio") else "WARN")

    fr = vp.freeze_frames(path)
    # a couple of short freezes on still-image scenes are expected; many long ones are not
    long_freezes = [(a, b) for a, b in fr if b - a > 2.5]
    r.passes["4_freeze_frames"] = _v(
        "WARN" if len(long_freezes) >= 3 else "OK",
        count=len(fr), long=len(long_freezes),
        note="short freezes on text-card / still scenes are expected (B53)")

    sync = vp.av_sync_drift(path)
    r.passes["5_av_sync"] = sync if sync.get("available") else _v("UNKNOWN", detail="not parseable in this build")

    col = vp.color_stats(path)
    if col.get("available"):
        spread = col.get("brightness_spread", 0.0)
        r.passes["6_color_consistency"] = _v(
            "WARN" if spread > 0.45 else "OK", brightness_spread=spread,
            brightness_mean=col.get("brightness_mean"))
    else:
        r.passes["6_color_consistency"] = _v("UNKNOWN")

    if reference_path and os.path.isfile(reference_path):
        r.passes["7_vmaf"] = vp.vmaf(reference_path, path)
    else:
        r.passes["7_vmaf"] = _v("SKIPPED", detail="no reference (encoded-vs-source only)")

    statuses = [p.get("status") for p in r.passes.values()]
    if "FAIL" in statuses:
        r.verdict = "FAIL"
    elif "WARN" in statuses or "OFF_TARGET" in statuses or "TRUE_PEAK_OVER" in statuses:
        r.verdict = "WARN"
    r.notes = [f"{k}: {p.get('status')}" for k, p in r.passes.items()
               if p.get("status") not in ("OK", "SKIPPED")]
    return r
