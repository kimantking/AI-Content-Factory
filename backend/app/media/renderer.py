from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.media.ffmpeg import run_ffmpeg
from app.media.subtitles import OverlayPNG
from app.providers.errors import ProviderError


@dataclass
class RenderScene:
    clip_path: str
    voice_path: str | None
    duration: float


@dataclass
class RenderPlan:
    scenes: list[RenderScene]
    width: int
    height: int
    fps: int = 30
    bgm_path: str | None = None
    music_volume: float = 0.16
    voice_volume: float = 1.0
    overlays: list[OverlayPNG] = field(default_factory=list)
    work_dir: str = ""

    @property
    def total_duration(self) -> float:
        return round(sum(s.duration for s in self.scenes), 3)


def _concat_demuxer(paths: list[str], list_file: str) -> None:
    with open(list_file, "w", encoding="utf-8") as f:
        for p in paths:
            f.write(f"file '{os.path.abspath(p)}'\n")


def _concat_video(clips: list[str], out: str, w: int, h: int, fps: int, work: str) -> str:
    lst = str(Path(work) / "clips.txt")
    _concat_demuxer(clips, lst)
    run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", lst,
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out,
    ])
    return out


def _build_voice_track(scenes: list[RenderScene], out: str, work: str) -> str | None:
    parts: list[str] = []
    for i, sc in enumerate(scenes):
        seg = str(Path(work) / f"voice_{i:03d}.wav")
        if sc.voice_path and os.path.isfile(sc.voice_path):
            run_ffmpeg([
                "-i", sc.voice_path,
                "-af", f"apad,atrim=0:{sc.duration:.3f},asetpts=PTS-STARTPTS",
                "-ar", "48000", "-ac", "2", seg,
            ])
        else:
            run_ffmpeg([
                "-f", "lavfi", "-t", f"{sc.duration:.3f}",
                "-i", "anullsrc=r=48000:cl=stereo", "-ar", "48000", "-ac", "2", seg,
            ])
        parts.append(seg)
    if not parts:
        return None
    lst = str(Path(work) / "voice.txt")
    _concat_demuxer(parts, lst)
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", lst, "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", out])
    return out


def _burn_overlays(video_in: str, overlays: list[OverlayPNG], out: str) -> str:
    if not overlays:
        run_ffmpeg(["-i", video_in, "-c", "copy", out])
        return out
    inputs: list[str] = ["-i", video_in]
    for ov in overlays:
        inputs += ["-i", ov.path]
    steps = []
    label = "0:v"
    for idx, ov in enumerate(overlays, start=1):
        nxt = f"v{idx}"
        steps.append(
            f"[{label}][{idx}:v]overlay=0:0:enable='between(t,{ov.start:.3f},{ov.end:.3f})'[{nxt}]"
        )
        label = nxt
    fc = ";".join(steps)
    run_ffmpeg([*inputs, "-filter_complex", fc, "-map", f"[{label}]",
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out])
    return out


def _mix_audio(voice: str | None, bgm: str | None, total: float, out: str,
               music_volume: float, voice_volume: float) -> str | None:
    if not voice and not bgm:
        return None
    if voice and bgm:
        # BGM ducked under narration (sidechaincompress); static fallback on failure.
        fc_duck = (
            f"[1:a]volume={music_volume},apad[bg];"
            f"[0:a]volume={voice_volume}[vo];"
            f"[bg][vo]sidechaincompress=threshold=0.02:ratio=12:attack=5:release=300[bgd];"
            f"[bgd][vo]amix=inputs=2:duration=first:dropout_transition=0,atrim=0:{total:.3f}[a]"
        )
        try:
            run_ffmpeg(["-i", voice, "-i", bgm, "-filter_complex", fc_duck,
                        "-map", "[a]", "-c:a", "aac", "-b:a", "160k", out])
            return out
        except ProviderError:
            fc_static = (
                f"[1:a]volume={music_volume * 0.6},apad[bg];"
                f"[0:a]volume={voice_volume}[vo];"
                f"[bg][vo]amix=inputs=2:duration=first:dropout_transition=0,atrim=0:{total:.3f}[a]"
            )
            run_ffmpeg(["-i", voice, "-i", bgm, "-filter_complex", fc_static,
                        "-map", "[a]", "-c:a", "aac", "-b:a", "160k", out])
            return out
    src = voice or bgm
    vol = voice_volume if voice else music_volume
    run_ffmpeg(["-i", src, "-af", f"volume={vol},apad,atrim=0:{total:.3f}",
                "-c:a", "aac", "-b:a", "160k", out])
    return out


def render_video(plan: RenderPlan, out_path: str) -> str:
    if not plan.scenes:
        raise ProviderError("render: no scenes", error_type="PROVIDER_ERROR")
    work = plan.work_dir or str(Path(out_path).parent / "_render")
    Path(work).mkdir(parents=True, exist_ok=True)

    v_concat = _concat_video([s.clip_path for s in plan.scenes],
                             str(Path(work) / "v_concat.mp4"),
                             plan.width, plan.height, plan.fps, work)
    v_sub = _burn_overlays(v_concat, plan.overlays, str(Path(work) / "v_sub.mp4"))
    voice = _build_voice_track(plan.scenes, str(Path(work) / "voice_full.wav"), work)
    audio = _mix_audio(voice, plan.bgm_path, plan.total_duration,
                       str(Path(work) / "mix.m4a"), plan.music_volume, plan.voice_volume)

    if audio:
        run_ffmpeg(["-i", v_sub, "-i", audio, "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-shortest",
                    "-movflags", "+faststart", out_path])
    else:
        run_ffmpeg(["-i", v_sub, "-an", "-c:v", "copy", "-movflags", "+faststart", out_path])
    return out_path
