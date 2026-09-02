"""Edit Decision V2 — frame-accurate, multi-track, non-destructive timeline
(B56, B57, B58, B59, B60).

Builds a `VideoTimeline` from planned scenes + directions. Source assets are never
mutated; every transform lives on a `TimelineClip`. Times are kept on a declared
timebase so fps conversion doesn't drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.video.schema import TimelineClip, VideoTimeline


def snap(t: float, fps: float) -> float:
    """Snap a seconds value to the nearest frame boundary for the timebase."""
    return round(round(t * fps) / fps, 6)


@dataclass
class EditHistoryEntry:
    scene_order: int
    version: int
    reason: str
    previous_asset: str | None
    new_asset: str | None
    quality_before: float | None
    quality_after: float | None
    cost: float = 0.0


def build_timeline(scenes: list[dict], directions: list, *, fps: float = 30.0,
                   width: int = 1080, height: int = 1920,
                   subtitle_blocks: list[dict] | None = None,
                   bgm_ref: str | None = None,
                   ducking: list | None = None) -> VideoTimeline:
    tl = VideoTimeline(fps=fps, timebase=fps, width=width, height=height)
    dmap = {getattr(d, "scene_order", i): d for i, d in enumerate(directions)}
    t = 0.0
    for i, s in enumerate(scenes):
        so = int(s.get("scene_order", i))
        dur = float(s.get("estimated_duration", s.get("duration", 4.0)))
        d = dmap.get(so)
        start, end = snap(t, fps), snap(t + dur, fps)
        ed = s.get("edit_decision", {}) or {}
        # VIDEO_MAIN
        tl.add(TimelineClip(
            track="VIDEO_MAIN",
            source_ref=s.get("still_path") or s.get("clip_path") or f"scene:{so}",
            start=start, end=end,
            source_in=float(ed.get("clip_start", 0.0)),
            source_out=float(ed.get("clip_end", dur)),
            speed=float(ed.get("speed", 1.0)),
            transform={"cinematic_motion": getattr(d, "cinematic_motion", s.get("camera_motion", "KEN_BURNS")) if d else s.get("camera_motion", "KEN_BURNS")},
            effects=list(ed.get("effects", [])),
            intent=getattr(d, "edit_intent", "CLARIFY") if d else "CLARIFY",
        ))
        # VOICE
        if s.get("voice_path"):
            tl.add(TimelineClip(track="VOICE", source_ref=s["voice_path"],
                                start=start, end=end, intent="NONE"))
        # SFX
        if s.get("sound_effect"):
            tl.add(TimelineClip(track="SFX", source_ref=f"sfx:{s['sound_effect']}",
                                start=start, end=snap(t + min(dur, 1.0), fps),
                                intent="TRANSITION"))
        t += dur

    total = snap(t, fps)
    # MUSIC as one clip with a ducking automation stored in transform
    if bgm_ref:
        tl.add(TimelineClip(track="MUSIC", source_ref=bgm_ref, start=0.0, end=total,
                            opacity=1.0, intent="ENERGY",
                            transform={"ducking": [vars(k) for k in (ducking or [])]}))
    # CAPTION blocks
    for b in (subtitle_blocks or []):
        tl.add(TimelineClip(track="CAPTION", source_ref="caption",
                            start=snap(float(b["start"]), fps), end=snap(float(b["end"]), fps),
                            transform={"text": b.get("text", ""),
                                       "kinetic": b.get("animation", "none")},
                            intent="CLARIFY"))
    return tl


def timeline_issues(tl: VideoTimeline) -> list[str]:
    issues: list[str] = []
    tracks = tl.tracks()
    main = sorted(tracks.get("VIDEO_MAIN", []), key=lambda c: c.start)
    for a, b in zip(main, main[1:]):
        if b.start < a.end - 1e-6:
            issues.append(f"VIDEO_MAIN overlap at {a.end:.3f}s")
        if b.start > a.end + 1e-6:
            issues.append(f"VIDEO_MAIN gap {b.start - a.end:.3f}s at {a.end:.3f}s")
    for c in tl.clips:
        if c.frame_end <= c.frame_start:
            issues.append(f"{c.track} clip has zero/negative frame length at {c.start:.3f}s")
    return issues
