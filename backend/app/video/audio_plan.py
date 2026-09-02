"""Audio / Sound Director (B38-B44, B84): music structure, ducking envelope,
SFX density, sound-design-follows-story, loudness target profiles.

Deterministic planning only. Real measurement (integrated LUFS / true peak) is in
`app.video.ffmpeg_probe.loudness()` and runs on the rendered file. Loudness
targets here are *configurable profile values*, explicitly NOT claimed to be
official platform requirements.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.video.schema import AudioPlan, DuckingKeyframe, MusicSection

# profile -> (integrated LUFS target, true-peak ceiling dBTP). Operator-tunable.
LOUDNESS_PROFILES = {
    "SOCIAL_QUIET": (-16.0, -1.5),
    "SOCIAL_STANDARD": (-14.0, -1.0),
    "PODCAST": (-16.0, -1.0),
    "PUNCHY": (-12.0, -1.0),
}


@dataclass
class _Section:
    label: str
    frac_start: float
    frac_end: float
    energy: float


# a generic 5-part music shape mapped onto the video's normalised timeline
_MUSIC_SHAPE = [
    _Section("intro", 0.0, 0.10, 0.35),
    _Section("build", 0.10, 0.45, 0.6),
    _Section("drop", 0.45, 0.72, 0.85),
    _Section("break", 0.72, 0.88, 0.5),
    _Section("outro", 0.88, 1.0, 0.3),
]

_BEAT_ENERGY = {
    "HOOK": 0.85, "SETUP": 0.4, "QUESTION": 0.5, "TENSION": 0.65, "DISCOVERY": 0.7,
    "PROOF": 0.45, "ESCALATION": 0.85, "CONTRAST": 0.6, "SURPRISE": 0.9,
    "PAYOFF": 0.55, "SUMMARY": 0.4, "CTA": 0.5, "AFTERTHOUGHT": 0.3,
}


def music_sections(total: float) -> list[MusicSection]:
    return [MusicSection(label=s.label, start=round(s.frac_start * total, 2),
                         end=round(s.frac_end * total, 2), target_energy=s.energy)
            for s in _MUSIC_SHAPE]


def ducking_envelope(scenes: list[dict], *, bed_gain: float = 0.18,
                     duck_gain: float = 0.05, attack: float = 0.25,
                     release: float = 0.45) -> list[DuckingKeyframe]:
    """Keyframed BGM gain: dip under narration, recover in gaps. Attack/release are
    slow enough (>=0.25s / >=0.45s) to avoid audible pumping (B40)."""
    kfs: list[DuckingKeyframe] = [DuckingKeyframe(t=0.0, music_gain=bed_gain)]
    t = 0.0
    for s in scenes:
        dur = float(s.get("estimated_duration", s.get("duration", 4.0)))
        has_voice = bool(s.get("voice_path") or s.get("narration"))
        if has_voice:
            kfs.append(DuckingKeyframe(t=round(t + attack, 3), music_gain=duck_gain))
            kfs.append(DuckingKeyframe(t=round(t + dur - release, 3), music_gain=duck_gain))
            kfs.append(DuckingKeyframe(t=round(t + dur, 3), music_gain=round((bed_gain + duck_gain) / 2, 3)))
        else:
            kfs.append(DuckingKeyframe(t=round(t + attack, 3), music_gain=bed_gain))
        t += dur
    kfs.append(DuckingKeyframe(t=round(t, 3), music_gain=round(bed_gain * 0.6, 3)))  # outro fade
    # dedupe near-identical adjacent keyframes
    out: list[DuckingKeyframe] = []
    for k in kfs:
        if out and abs(out[-1].t - k.t) < 0.02 and abs(out[-1].music_gain - k.music_gain) < 0.005:
            continue
        out.append(k)
    return out


def sfx_density(scenes: list[dict], total: float) -> tuple[float, str]:
    n = sum(1 for s in scenes if s.get("sound_effect"))
    per10 = n / max(1.0, total / 10.0)
    return round(per10, 2), ("HIGH" if per10 > 3.5 else "OK")


def sound_energy_curve(beats: list[str]) -> list[float]:
    """Audio energy should track the story arc (B84), not sit flat."""
    return [round(_BEAT_ENERGY.get(b, 0.5), 2) for b in beats]


def plan_audio(scenes: list[dict], beats: list[str], *, profile: str = "SOCIAL_STANDARD",
               music_style: str = "AMBIENT") -> AudioPlan:
    total = sum(float(s.get("estimated_duration", s.get("duration", 4.0))) for s in scenes) or 1.0
    lufs, tp = LOUDNESS_PROFILES.get(profile, LOUDNESS_PROFILES["SOCIAL_STANDARD"])
    dens, flag = sfx_density(scenes, total)
    notes: list[str] = []
    if flag == "HIGH":
        notes.append(f"SFX density {dens}/10s is high — cut to attention/transition/impact only")
    curve = sound_energy_curve(beats)
    if curve and max(curve) - min(curve) < 0.2:
        notes.append("sound-design energy is nearly flat — let it follow the story arc")
    return AudioPlan(
        music_sections=music_sections(total),
        ducking=ducking_envelope(scenes),
        sfx_density=dens, sfx_density_flag=flag,
        loudness_target_lufs=lufs, true_peak_ceiling_dbtp=tp,
        energy_curve=curve, notes=notes,
    )
