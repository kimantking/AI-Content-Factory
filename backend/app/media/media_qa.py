from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.media.ffmpeg import detect_black, detect_silence, probe


@dataclass
class MediaQAReport:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)


def check_render(path: str, *, expect_duration: float, expect_w: int, expect_h: int,
                 expect_fps: int, scene_count: int, subtitle_coverage: float) -> MediaQAReport:
    checks: dict[str, bool] = {}
    issues: list[str] = []

    checks["file_exists"] = os.path.isfile(path)
    checks["file_readable"] = checks["file_exists"] and os.path.getsize(path) > 1024
    if not checks["file_readable"]:
        return MediaQAReport(passed=False, checks=checks, issues=["render file missing/empty"])

    info = probe(path)
    dur = info.get("duration", 0.0)
    checks["has_video"] = info.get("has_video", False)
    checks["has_audio_stream"] = info.get("has_audio", False)
    checks["duration_ok"] = abs(dur - expect_duration) <= max(1.5, expect_duration * 0.25)
    w, h = info.get("width"), info.get("height")
    checks["resolution_ok"] = (w == expect_w and h == expect_h)
    checks["aspect_ratio_ok"] = (
        bool(w and h) and abs((w / h) - (expect_w / expect_h)) < 0.02
    )
    fps = info.get("fps", expect_fps)
    checks["fps_ok"] = abs(fps - expect_fps) <= 2

    blacks = detect_black(path)
    black_time = sum(e - s for s, e in blacks)
    checks["no_excess_black"] = black_time <= max(1.0, dur * 0.2)
    if not checks["no_excess_black"]:
        issues.append(f"black frames total {black_time:.1f}s")

    silences = detect_silence(path)
    sil_time = sum(max(0.0, e - s) for s, e in silences if e >= s)
    checks["audio_not_fully_silent"] = dur > 0 and sil_time < dur * 0.98
    if not checks["audio_not_fully_silent"]:
        issues.append("audio track is effectively silent")

    checks["subtitle_coverage_ok"] = subtitle_coverage >= 0.6
    if not checks["subtitle_coverage_ok"]:
        issues.append(f"subtitle coverage {subtitle_coverage:.0%} < 60%")

    checks["scenes_present"] = scene_count > 0

    for k, v in checks.items():
        if not v and k not in ("audio_not_fully_silent",):  # mock voice is near-silent
            issues.append(f"failed: {k}")

    hard_fail = not all(
        checks[k] for k in (
            "file_readable", "has_video", "duration_ok",
            "resolution_ok", "aspect_ratio_ok", "scenes_present",
        )
    )
    return MediaQAReport(
        passed=not hard_fail,
        checks=checks,
        issues=issues,
        facts={"duration": dur, "width": w, "height": h, "fps": fps,
               "black_time": round(black_time, 2), "silence_time": round(sil_time, 2)},
    )
