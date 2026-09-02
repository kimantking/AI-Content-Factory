"""Pacing engines: Visual Refresh, Information Density, Cognitive Load, Focus,
Effect Budget, Editing Intent, Pattern Interrupt (B76, B77, B78, B79, B80, B81, B82).

All deterministic. These produce advisory metrics + per-scene guidance; they do
not force a rhythm.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = re.compile(r"\d[\d,.%]*")
_WORD = re.compile(r"[\w가-힣]+")

# per content-type baseline: seconds of screen-time before a meaningful visual change
_REFRESH_BASELINE = {
    "SHORTS": (1.6, 4.5), "REEL": (1.8, 5.0), "TIKTOK": (1.4, 4.0),
    "LONG": (4.0, 12.0), "EXPLAINER": (3.5, 10.0),
}


@dataclass
class PacingReport:
    visual_refresh_avg: float = 0.0
    visual_refresh_flag: str = "OK"        # OK | TOO_FAST | TOO_SLOW
    info_density: list[float] = field(default_factory=list)   # per scene
    cognitive_load: list[float] = field(default_factory=list)
    overload_scenes: list[int] = field(default_factory=list)
    primary_focus: list[str] = field(default_factory=list)
    edit_intent: list[str] = field(default_factory=list)
    effect_budget: list[int] = field(default_factory=list)
    reduce_actions: dict = field(default_factory=dict)   # scene_order -> action
    notes: list[str] = field(default_factory=list)


def _duration(s: dict) -> float:
    return float(s.get("estimated_duration", s.get("duration", 4.0))) or 4.0


def visual_refresh(scenes: list[dict], directions: list, content_kind: str) -> tuple[float, str]:
    dmap = {getattr(d, "scene_order", i): d for i, d in enumerate(directions)}
    changes = 0
    prev_key = None
    total = 0.0
    for i, s in enumerate(scenes):
        total += _duration(s)
        d = dmap.get(int(s.get("scene_order", i)))
        key = (s.get("visual_type"), s.get("camera_motion"),
               getattr(d, "shot_size", None) if d else None,
               getattr(d, "primary_focus", None) if d else None)
        if key != prev_key:
            changes += 1
        prev_key = key
    avg = total / max(1, changes)
    lo, hi = _REFRESH_BASELINE.get(content_kind.upper(), _REFRESH_BASELINE["SHORTS"])
    flag = "TOO_FAST" if avg < lo else "TOO_SLOW" if avg > hi else "OK"
    return round(avg, 2), flag


def _new_info_units(narr: str, caption: str, has_chart: bool) -> float:
    t = narr or ""
    units = 0.0
    units += len(_NUM.findall(t)) * 1.0                       # each number = 1 unit
    units += min(3, len(_WORD.findall(t)) / 12.0)             # spoken content
    if caption and caption.strip() and caption.strip() != t.strip():
        units += 0.8                                          # caption adds a channel
    if has_chart:
        units += 1.4
    return units


def analyze(scenes: list[dict], directions: list, *, content_kind: str = "SHORTS") -> PacingReport:
    if not scenes:
        return PacingReport()
    dmap = {getattr(d, "scene_order", i): d for i, d in enumerate(directions)}
    dens: list[float] = []
    load: list[float] = []
    overload: list[int] = []
    focus: list[str] = []
    intent: list[str] = []
    budget: list[int] = []

    for i, s in enumerate(scenes):
        dur = _duration(s)
        so = int(s.get("scene_order", i))
        d = dmap.get(so)
        has_chart = s.get("visual_type") in ("CHART",)
        caption = s.get("subtitle_text") or s.get("narration") or ""
        u = _new_info_units(s.get("narration", ""), caption, has_chart)
        density = u / max(1.0, dur)
        dens.append(round(density, 3))

        # cognitive load: simultaneous channels competing for attention
        channels = 1  # narration
        if caption and caption.strip() != (s.get("narration") or "").strip():
            channels += 1
        if has_chart or s.get("visual_type") == "SCREENSHOT":
            channels += 1
        if s.get("sound_effect"):
            channels += 0.5
        motion_e = getattr(d, "motion_energy", "MEDIUM") if d else "MEDIUM"
        if motion_e == "HIGH":
            channels += 0.5
        cl = min(1.0, (channels - 1) / 3.0 + max(0.0, density - 1.2) * 0.25)
        load.append(round(cl, 3))
        if cl >= 0.75:
            overload.append(so)

        # primary focus
        if has_chart:
            focus.append("chart")
        elif s.get("visual_type") == "SCREENSHOT":
            focus.append("proof")
        elif _NUM.search(s.get("narration") or ""):
            focus.append("text")
        elif getattr(d, "story_beat", "") in ("CONTRAST", "SURPRISE"):
            focus.append("action")
        else:
            focus.append("scene")

        # editing intent
        beat = getattr(d, "story_beat", "SETUP") if d else "SETUP"
        intent.append({
            "HOOK": "ENERGY", "PROOF": "PROOF", "SURPRISE": "EMPHASIS",
            "CONTRAST": "EMPHASIS", "PAYOFF": "EMPHASIS", "CTA": "ORIENTATION",
            "SETUP": "ORIENTATION", "SUMMARY": "CLARIFY",
        }.get(beat, "CLARIFY"))

        # effect budget: fewer when load already high; more for hook/surprise
        base = 2
        if beat in ("HOOK", "SURPRISE"):
            base = 3
        if cl >= 0.7:
            base = 1
        budget.append(base)

    # cognitive-load reduction actions per overloaded scene (B35)
    reduce_actions: dict[int, str] = {}
    for so in overload:
        i = next((k for k, s in enumerate(scenes) if int(s.get("scene_order", k)) == so), 0)
        s = scenes[i]
        cap = s.get("subtitle_text") or s.get("narration") or ""
        if cap and cap.strip() != (s.get("narration") or "").strip():
            reduce_actions[so] = "reduce_caption"
        elif s.get("visual_type") in ("CHART", "SCREENSHOT"):
            reduce_actions[so] = "simplify_visual"
        elif s.get("sound_effect") or (i < len(load) and load[i] > 0.85):
            reduce_actions[so] = "reduce_effect"
        else:
            reduce_actions[so] = "extend_scene"

    avg, flag = visual_refresh(scenes, directions, content_kind)
    notes: list[str] = []
    if flag == "TOO_FAST":
        notes.append(f"visual refresh {avg}s is faster than the {content_kind} comfort band")
    if flag == "TOO_SLOW":
        notes.append(f"visual refresh {avg}s is slower than the {content_kind} comfort band")
    if overload:
        notes.append(f"cognitive overload at scenes {overload} — thin one channel")
    if sum(dens) / len(dens) < 0.25 and len(scenes) > 4:
        notes.append("low information density overall — video may feel like filler")

    return PacingReport(
        visual_refresh_avg=avg, visual_refresh_flag=flag, info_density=dens,
        cognitive_load=load, overload_scenes=overload, primary_focus=focus,
        edit_intent=intent, effect_budget=budget, notes=notes,
        reduce_actions=reduce_actions,
    )
