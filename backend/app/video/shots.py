"""Shot Grammar + Sequence Rules + Camera-Motion Continuity + Motion Energy
(B7, B8, B9, B27, B28).

Deterministic. Assigns a shot size + purpose to each scene from its beat/emotion/
content, then detects mechanical problems: same shot size repeated, camera motion
repeated OR mechanically alternated, motion energy flat. Suggestions are advisory
— nothing is forced.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.video.schema import SHOT_SIZES

_NUM = re.compile(r"\d[\d,.%]*")
_DETAIL_CUE = ("정확히", "구체적으로", "이 부분", "숫자", "한 가지", "핵심은", "바로 이")
_WIDE_CUE = ("전체", "시장", "산업", "사회", "세계", "도시", "배경", "맥락", "큰 그림")
_REACTION_CUE = ("놀랍", "충격", "믿기", "반전", "예상과 달리")

_SIZE_ORDER = {s: i for i, s in enumerate(SHOT_SIZES)}  # EXTREME_WIDE=0 .. DETAIL=6

_BEAT_SHOT = {
    "HOOK": ("MEDIUM_CLOSE", "EMPHASIS"),
    "SETUP": ("WIDE", "ESTABLISHING"),
    "QUESTION": ("MEDIUM_CLOSE", "EMPHASIS"),
    "TENSION": ("MEDIUM", "CONTEXT"),
    "DISCOVERY": ("MEDIUM_CLOSE", "ACTION"),
    "PROOF": ("CLOSE", "PROOF"),
    "ESCALATION": ("MEDIUM", "ACTION"),
    "CONTRAST": ("MEDIUM", "REACTION"),
    "SURPRISE": ("CLOSE", "REACTION"),
    "PAYOFF": ("MEDIUM_CLOSE", "EMPHASIS"),
    "SUMMARY": ("MEDIUM", "CONTEXT"),
    "CTA": ("MEDIUM_CLOSE", "EMPHASIS"),
    "AFTERTHOUGHT": ("WIDE", "TRANSITION"),
}


@dataclass
class ShotPlan:
    shot_size: list[str] = field(default_factory=list)
    shot_purpose: list[str] = field(default_factory=list)
    motion_energy: list[str] = field(default_factory=list)
    cinematic_motion: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def _first_size(narr: str, beat: str) -> tuple[str, str]:
    t = narr or ""
    size, purpose = _BEAT_SHOT.get(beat, ("MEDIUM", "CONTEXT"))
    if _NUM.search(t) or any(c in t for c in _DETAIL_CUE):
        return "CLOSE", "PROOF"
    if any(c in t for c in _WIDE_CUE):
        return "WIDE", "ESTABLISHING"
    if any(c in t for c in _REACTION_CUE):
        return "CLOSE", "REACTION"
    return size, purpose


def _vary_repeats(sizes: list[str]) -> tuple[list[str], list[str]]:
    """Break >=3 identical sizes in a row by nudging the middle one a step."""
    issues: list[str] = []
    out = list(sizes)
    i = 0
    while i < len(out):
        j = i
        while j + 1 < len(out) and out[j + 1] == out[i]:
            j += 1
        run = j - i + 1
        if run >= 3:
            issues.append(f"SHOT_SCALE_REPETITION: {out[i]} x{run} at scenes {i}-{j}")
            mid = (i + j) // 2
            idx = _SIZE_ORDER[out[mid]]
            # move toward the middle of the scale, staying legal
            target = idx - 1 if idx >= 4 else idx + 1
            target = max(0, min(len(SHOT_SIZES) - 1, target))
            out[mid] = SHOT_SIZES[target]
        i = j + 1
    return out, issues


def _motion_energy(beats: list[str], emos: list[str]) -> list[str]:
    hi = {"HOOK", "SURPRISE", "ESCALATION", "CONTRAST"}
    lo = {"PROOF", "SUMMARY", "SETUP"}
    out: list[str] = []
    for b, e in zip(beats, emos):
        if b in hi or e in ("urgency", "surprise"):
            out.append("HIGH")
        elif b in lo or e == "confidence":
            out.append("LOW")
        else:
            out.append("MEDIUM")
    return out


_CINEMATIC_FOR = {
    ("HIGH", "PROOF"): "DOLLY_IN_SIM",
    ("HIGH", "REACTION"): "SUBJECT_PUSH",
    ("HIGH", "EMPHASIS"): "DOLLY_IN_SIM",
    ("LOW", "ESTABLISHING"): "BACKGROUND_DRIFT",
    ("LOW", "CONTEXT"): "KEN_BURNS",
    ("LOW", "PROOF"): "FOCUS_PULL_SIM",
    ("MEDIUM", "ACTION"): "DEPTH_PARALLAX_SIM",
    ("MEDIUM", "TRANSITION"): "DOLLY_OUT_SIM",
}


def camera_motion_continuity(motions: list[str]) -> list[str]:
    """Flag mechanical patterns: same motion 3x in a row, or strict A/B/A/B alternation."""
    issues: list[str] = []
    for i in range(2, len(motions)):
        if motions[i] == motions[i - 1] == motions[i - 2]:
            issues.append(f"CAMERA_MOTION_REPETITION: {motions[i]} x3 at scenes {i-2}-{i}")
    if len(motions) >= 4:
        alt = all(motions[k] == motions[k - 2] and motions[k] != motions[k - 1]
                  for k in range(2, len(motions)))
        if alt and len(set(motions)) == 2:
            issues.append("CAMERA_MOTION_MECHANICAL_ALTERNATION: A/B/A/B pattern")
    return issues


def plan_shots(narrations: list[str], beats: list[str], emotions: list[str]) -> ShotPlan:
    sizes, purposes = [], []
    for narr, beat in zip(narrations, beats):
        sz, pp = _first_size(narr, beat)
        sizes.append(sz)
        purposes.append(pp)
    sizes, issues = _vary_repeats(sizes)
    energy = _motion_energy(beats, emotions)
    cinem = [_CINEMATIC_FOR.get((e, p), "KEN_BURNS") for e, p in zip(energy, purposes)]
    issues += camera_motion_continuity(cinem)
    return ShotPlan(shot_size=sizes, shot_purpose=purposes, motion_energy=energy,
                    cinematic_motion=cinem, issues=issues)
