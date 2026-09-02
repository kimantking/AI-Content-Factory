"""Creative QA V2 (B47) — deterministic checks for the "feels like a template"
failure modes: AI-visual overuse, generic stock, repetitive zoom / captions /
transitions, generic music, flat voice, visual mismatch, weak story arc,
over/under-editing, same-recent-format.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class CreativeQAReport:
    checks: dict[str, str] = field(default_factory=dict)   # name -> OK | WARN | FAIL
    score: float = 1.0
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.score >= 0.6 and "FAIL" not in self.checks.values()


def _ratio(items, pred) -> float:
    if not items:
        return 0.0
    return sum(1 for x in items if pred(x)) / len(items)


def evaluate(scenes: list[dict], directions: list, *, voice_plan=None,
             audio_plan=None, music_style: str = "AMBIENT",
             recent_style: dict | None = None) -> CreativeQAReport:
    n = max(1, len(scenes))
    dmap = {getattr(d, "scene_order", i): d for i, d in enumerate(directions)}
    checks: dict[str, str] = {}
    notes: list[str] = []

    vtypes = [s.get("visual_type") for s in scenes]
    ai_ratio = _ratio(vtypes, lambda v: v in ("AI_IMAGE", "AI_VIDEO"))
    checks["ai_visual_overuse"] = "FAIL" if ai_ratio > 0.8 else "WARN" if ai_ratio > 0.6 else "OK"
    if ai_ratio > 0.6:
        notes.append(f"{ai_ratio:.0%} of scenes are AI-generated visuals")

    stock_ratio = _ratio(vtypes, lambda v: v == "STOCK_VIDEO")
    checks["generic_stock"] = "WARN" if stock_ratio > 0.5 else "OK"

    motions = [s.get("camera_motion") for s in scenes]
    mc = Counter(motions)
    checks["repetitive_zoom"] = "FAIL" if mc and mc.most_common(1)[0][1] > n * 0.6 else \
        "WARN" if mc and mc.most_common(1)[0][1] > n * 0.45 else "OK"

    kinetic = [getattr(dmap.get(int(s.get("scene_order", i)), None), "kinetic_caption", "NONE")
               for i, s in enumerate(scenes)]
    kin_ratio = _ratio(kinetic, lambda k: k not in ("NONE", None))
    checks["repetitive_captions"] = "WARN" if kin_ratio > 0.7 else "OK"
    if kin_ratio > 0.7:
        notes.append("kinetic captions on most scenes — reserve them for key moments")

    transitions = [s.get("transition", "CUT") for s in scenes]
    tc = Counter(transitions)
    checks["repetitive_transitions"] = "OK" if len(tc) > 1 or transitions.count("CUT") == n else "WARN"

    checks["generic_music"] = "WARN" if music_style.upper() in ("AMBIENT", "GENERIC", "") else "OK"

    if voice_plan is not None:
        checks["flat_voice"] = "WARN" if getattr(voice_plan, "consistency_score", 1.0) > 0.98 and \
            len(getattr(voice_plan, "phrases", [])) > 3 else "OK"
        if checks["flat_voice"] == "WARN":
            notes.append("voice performance barely varies across the whole script")
    else:
        checks["flat_voice"] = "OK"

    beats = [getattr(dmap.get(int(s.get("scene_order", i)), None), "story_beat", "SETUP")
             for i, s in enumerate(scenes)]
    distinct_beats = len(set(beats))
    checks["weak_story_arc"] = "FAIL" if distinct_beats < 2 else "WARN" if distinct_beats < 3 else "OK"

    eff_budget = [getattr(dmap.get(int(s.get("scene_order", i)), None), "effect_budget", 2)
                  for i, s in enumerate(scenes)]
    avg_eff = sum(eff_budget) / n
    checks["over_editing"] = "WARN" if avg_eff > 2.6 else "OK"
    checks["under_editing"] = "WARN" if (len(set(vtypes)) <= 1 and len(set(motions)) <= 1) else "OK"

    visual_ev = sum(1 for i, s in enumerate(scenes)
                    if getattr(dmap.get(int(s.get("scene_order", i)), None), "visual_evidence", False)
                    and s.get("visual_type") in ("AI_IMAGE",))
    checks["visual_mismatch"] = "WARN" if visual_ev >= 2 else "OK"
    if visual_ev >= 2:
        notes.append(f"{visual_ev} scenes make a claim but show a generic AI image, not evidence")

    if recent_style and recent_style.get("overused_motion_patterns"):
        checks["same_recent_format"] = "WARN"
        notes.append("style fingerprint matches recent videos — vary it")
    else:
        checks["same_recent_format"] = "OK"

    fails = sum(1 for v in checks.values() if v == "FAIL")
    warns = sum(1 for v in checks.values() if v == "WARN")
    score = max(0.0, 1.0 - 0.25 * fails - 0.08 * warns)
    return CreativeQAReport(checks=checks, score=round(score, 3), notes=notes)
