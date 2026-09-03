"""Video Quality Score V2 + Bad-Scene Detector + Auto-Repair map + before/after
guard (B49, B52, B61, B62, B63, B67, B93).

Deterministic scoring over the plan + whatever real QA facts are available. No
"quality theatre": an enhancement counts as an improvement only if a measured
before/after says so (`improved()`).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.video.schema import VideoQualityScoreV2

_DIMS = (
    "story", "hook", "retention_design", "visual_relevance", "shot_variety",
    "continuity", "edit_rhythm", "voice", "sound_design", "subtitle", "graphics",
    "color", "technical", "naturalness", "originality", "platform_fit",
)

BAD_SCENE_FLAGS = (
    "LOW_RELEVANCE", "LOW_QUALITY", "VISUAL_REPETITION", "BAD_CROP", "WRONG_ASPECT",
    "TEXT_ERROR", "TIMING_ERROR", "BORING", "VOICE_ISSUE", "AUDIO_ISSUE", "SOURCE_RISK",
)

REPAIR_STRATEGY = {
    "LOW_RELEVANCE": "broll_reselect",
    "BAD_CROP": "smart_reframe",
    "WRONG_ASPECT": "smart_reframe",
    "LOW_QUALITY": "alternate_or_enhance",
    "VISUAL_REPETITION": "vary_shot_or_motion",
    "TIMING_ERROR": "realign_timings",
    "AUDIO_ISSUE": "remix_audio",
    "VOICE_ISSUE": "resynthesize_phrase",
    "BORING": "visual_replan",
    "TEXT_ERROR": "regen_caption",
    "SOURCE_RISK": "replace_source",
}


@dataclass
class BadScene:
    scene_order: int
    flags: list[str]
    strategies: list[str]
    confidence: float           # of the detection


def detect_bad_scenes(scenes: list[dict], directions: list, *,
                      weak_scenes: list[int] | None = None,
                      boredom_spans: list[tuple[int, int]] | None = None) -> list[BadScene]:
    weak = set(weak_scenes or [])
    boring = set()
    for a, b in (boredom_spans or []):
        boring.update(range(a, b + 1))
    dmap = {getattr(d, "scene_order", i): d for i, d in enumerate(directions)}
    out: list[BadScene] = []
    seen_visual: dict[tuple, int] = {}
    for i, s in enumerate(scenes):
        so = int(s.get("scene_order", i))
        flags: list[str] = []
        d = dmap.get(so)
        # repetition
        key = (s.get("visual_type"), s.get("camera_motion"))
        seen_visual[key] = seen_visual.get(key, 0) + 1
        if seen_visual[key] >= 4:
            flags.append("VISUAL_REPETITION")
        if so in boring:
            flags.append("BORING")
        if so in weak or (so + 1) in weak:
            flags.append("LOW_RELEVANCE")
        if d and getattr(d, "cognitive_load", 0.0) >= 0.85:
            flags.append("TEXT_ERROR")  # too much on screen ~ readability risk
        dur = float(s.get("estimated_duration", s.get("duration", 4.0)))
        if dur < 1.2 or dur > 20.0:
            flags.append("TIMING_ERROR")
        if s.get("visual_type") in ("AI_VIDEO",) and s.get("provider_mode") == "MOCK":
            pass  # mock is fine
        if flags:
            out.append(BadScene(
                scene_order=so, flags=flags,
                strategies=[REPAIR_STRATEGY[f] for f in flags if f in REPAIR_STRATEGY],
                confidence=round(min(1.0, 0.4 + 0.2 * len(flags)), 2),
            ))
    return out


def score(*, story_report, retention_report, pacing_report, shot_plan,
          voice_plan, audio_plan, content_qa: dict | None = None,
          media_qa: dict | None = None, ai_video_ratio: float = 0.0,
          naturalness: float | None = None) -> VideoQualityScoreV2:
    content_qa = content_qa or {}
    media_qa = media_qa or {}
    d: dict[str, float] = {}

    beats = [b.beat for b in getattr(story_report, "story_arc", [])] or \
            getattr(story_report, "beats", [])
    d["story"] = 0.55 + (0.25 if "PAYOFF" in beats or "DISCOVERY" in beats else 0.0) + \
                 (0.1 if "HOOK" in beats else 0.0) + (0.1 if len(set(beats)) >= 4 else 0.0)
    d["hook"] = retention_report.first_second_strength
    d["retention_design"] = max(0.0, 1.0 - retention_report.boredom_risk) * \
                            (0.7 + 0.3 * (1.0 if retention_report.early_payoff else 0.0))
    cs = content_qa.get("scores", {})
    d["visual_relevance"] = cs.get("content_consistency", 0.7)
    d["shot_variety"] = min(1.0, 0.4 + 0.12 * len(set(shot_plan.shot_size)) +
                            (0.15 if not any("REPETITION" in x for x in shot_plan.issues) else 0.0))
    d["continuity"] = 1.0 - min(0.5, 0.12 * len(shot_plan.issues))
    d["edit_rhythm"] = {"OK": 0.85, "TOO_FAST": 0.55, "TOO_SLOW": 0.6}.get(
        pacing_report.visual_refresh_flag, 0.7)
    d["voice"] = voice_plan.consistency_score * 0.9 + 0.1
    d["sound_design"] = 0.5 + (0.25 if audio_plan.energy_curve and
                               max(audio_plan.energy_curve) - min(audio_plan.energy_curve) >= 0.2 else 0.0) + \
                        (0.25 if audio_plan.sfx_density_flag == "OK" else 0.0)
    d["subtitle"] = cs.get("subtitle_quality", 0.7)
    d["graphics"] = 0.7
    d["color"] = 0.72
    d["technical"] = 0.9 if media_qa.get("passed") else 0.45
    d["naturalness"] = naturalness if naturalness is not None else \
        (cs.get("originality", 0.7))
    d["originality"] = max(0.3, 1.0 - ai_video_ratio * 0.5)
    d["platform_fit"] = cs.get("platform_fit", 0.8)

    d = {k: round(min(1.0, max(0.0, d.get(k, 0.6))), 3) for k in _DIMS}
    weights = {k: 1.0 for k in _DIMS}
    weights.update({"story": 1.6, "hook": 1.6, "retention_design": 1.5,
                    "visual_relevance": 1.4, "technical": 1.3, "naturalness": 1.3})
    overall = round(sum(d[k] * weights[k] for k in _DIMS) / sum(weights.values()), 3)
    weak = [k for k, v in d.items() if v < 0.5]
    notes = []
    if weak:
        notes.append("weak dimensions: " + ", ".join(weak))
    return VideoQualityScoreV2(dimensions=d, overall=overall, weak=weak, notes=notes)


def score_100(vscore: VideoQualityScoreV2) -> dict:
    """0..100 view of the quality score (B49)."""
    return {
        "overall": round(vscore.overall * 100, 1),
        "dimensions": {k: round(v * 100, 1) for k, v in vscore.dimensions.items()},
        "passed": vscore.passed,
        "weak": vscore.weak,
    }


_REPAIR_ORDER = ["SOURCE_RISK", "TEXT_ERROR", "TIMING_ERROR", "BAD_CROP", "WRONG_ASPECT",
                 "LOW_RELEVANCE", "CONTINUITY_ERROR", "COGNITIVE_OVERLOAD", "LOW_QUALITY",
                 "VOICE_ISSUE", "AUDIO_ISSUE", "VISUAL_REPETITION", "BORING"]


def plan_repairs(bad_scenes: list, *, max_repairs: int = 4) -> list[dict]:
    """Turn bad-scene flags into an ordered, de-duplicated repair worklist
    (B45). Full re-render is never in this list — it is the caller's last resort."""
    items: list[tuple[int, int, str, str]] = []
    for b in bad_scenes:
        so = getattr(b, "scene_order", b.get("scene_order") if isinstance(b, dict) else 0)
        flags = getattr(b, "flags", b.get("flags", []) if isinstance(b, dict) else [])
        for f in flags:
            pri = _REPAIR_ORDER.index(f) if f in _REPAIR_ORDER else 99
            strat = REPAIR_STRATEGY.get(f, "manual_review")
            items.append((pri, so, f, strat))
    items.sort()
    seen: set = set()
    out: list[dict] = []
    for _pri, so, flag, strat in items:
        key = (so, strat)
        if key in seen:
            continue
        seen.add(key)
        out.append({"scene_order": so, "flag": flag, "strategy": strat})
        if len(out) >= max_repairs:
            break
    return out


def continuity_score(shot_plan) -> float:
    """0..1 — 1.0 minus a penalty per continuity issue on the shot plan (B11)."""
    issues = getattr(shot_plan, "issues", [])
    return round(max(0.0, 1.0 - 0.12 * len(issues)), 3)


def improved(before: float | None, after: float | None, *, min_gain: float = 0.02) -> bool:
    """Guard against quality theatre (B67): an enhancement is only 'better' if a
    measured metric actually went up by a meaningful margin."""
    if before is None or after is None:
        return False
    return (after - before) >= min_gain
