"""Video Director (B1) — orchestrates the deterministic Director engines into one
`VideoCreativePlan`. No LLM call. Pure function of its inputs.
"""
from __future__ import annotations

from app.video import audio_plan as _audio
from app.video import broll as _broll
from app.video import color as _color
from app.video import pacing as _pacing
from app.video import retention as _retention
from app.video import shots as _shots
from app.video import story as _story
from app.video import voice_plan as _voice
from app.video.router import route
from app.video.schema import SceneDirection, VideoCreativePlan

# content_type -> (is_short, pacing content-kind, edit profile)
_PROFILE_BY_CT = {
    "SHORT_VIDEO": (True, "SHORTS", "SHORT_FORM"),
    "SHORTS": (True, "SHORTS", "SHORT_FORM"),
    "REEL": (True, "REEL", "SHORT_FORM"),
    "TIKTOK": (True, "TIKTOK", "SHORT_FORM"),
    "CLIP": (True, "SHORTS", "SHORT_FORM"),
    "LONG_VIDEO": (False, "LONG", "LONG_FORM"),
    "EXPLAINER": (False, "EXPLAINER", "LONG_FORM"),
    "VIDEO": (True, "SHORTS", "SHORT_FORM"),
}


def direct_video(*, platform: str, content_type: str, scenes: list[dict],
                 profile: str = "STANDARD", brand: str = "default",
                 style: str = "EXPLAINER", budget_usd: float = 1.0,
                 risk: str = "LOW", opportunity_score: float = 50.0,
                 gpu_available: bool = False, ai_video_ratio: float = 0.0,
                 recent_style: dict | None = None) -> VideoCreativePlan:
    is_short, pace_kind, edit_profile = _PROFILE_BY_CT.get(
        content_type.upper(), (True, "SHORTS", "SHORT_FORM"))
    narrations = [s.get("narration", "") for s in scenes]

    beats, emos, arc = _story.build_story_arc(narrations)
    shot_plan = _shots.plan_shots(narrations, beats, emos)

    # first pass of scene directions (needed by pacing / retention / boredom)
    directions: list[SceneDirection] = []
    for i, s in enumerate(scenes):
        directions.append(SceneDirection(
            scene_order=int(s.get("scene_order", i)),
            story_beat=beats[i], emotion_intent=emos[i],
            shot_size=shot_plan.shot_size[i], shot_purpose=shot_plan.shot_purpose[i],
            motion_energy=shot_plan.motion_energy[i],
            cinematic_motion=shot_plan.cinematic_motion[i],
        ))

    pacing = _pacing.analyze(scenes, directions, content_kind=pace_kind)
    retention = _retention.analyze(scenes, directions, is_short=is_short)
    voice = _voice.plan_voice(scenes, directions, brand_style=style)
    audio = _audio.plan_audio(scenes, beats, music_style="AMBIENT")

    # finalise directions with pacing/retention outputs
    boring = {x for a, b in retention.boredom_spans for x in range(a, b + 1)}
    interrupts = set(retention.pattern_interrupts)
    for i, d in enumerate(directions):
        d.primary_focus = pacing.primary_focus[i]
        d.edit_intent = pacing.edit_intent[i]
        d.effect_budget = pacing.effect_budget[i]
        d.cognitive_load = pacing.cognitive_load[i]
        d.information_density = pacing.info_density[i]
        d.pattern_interrupt = d.scene_order in interrupts
        d.visual_evidence = _broll.visual_evidence_priority(scenes[i])
        if d.visual_evidence:
            d.notes.append("prefer a chart/screenshot/real doc over a generic AI image")
        if d.scene_order in boring:
            d.notes.append("low-variation span — change shot size / motion / focus here")
        # kinetic caption only on high-impact beats
        if d.story_beat in ("HOOK", "PROOF", "SURPRISE", "PAYOFF") and is_short:
            d.kinetic_caption = "NUMBER_PUNCH" if d.primary_focus in ("text", "chart", "proof") else "WORD_REVEAL"

    # editor memory: nudge away from an overused motion pattern
    warnings: list[str] = list(shot_plan.issues) + pacing.notes + retention.notes + \
        voice.notes + audio.notes
    if recent_style and recent_style.get("overused_motion_patterns"):
        warnings.append("editor memory: recent videos overuse "
                        f"{recent_style['overused_motion_patterns']} — vary motion this time")

    # budget distribution: weight high-impact scenes
    high_impact = _high_impact_scenes(directions, retention)
    total_w = 0.0
    dist: dict[int, float] = {}
    for d in directions:
        w = 1.0
        if d.scene_order in high_impact:
            w = 2.0
        if d.story_beat in ("SETUP", "SUMMARY", "AFTERTHOUGHT"):
            w = 0.7
        dist[d.scene_order] = w
        total_w += w
    dist = {k: round(v / total_w, 4) for k, v in dist.items()}

    routing = route(platform=platform, content_type=content_type, profile=profile,
                    budget_usd=budget_usd, risk=risk, opportunity_score=opportunity_score,
                    gpu_available=gpu_available, is_short=is_short)
    skills = {sid: "required" for sid in routing.required}
    skills.update({sid: "optional" for sid in routing.optional})
    skills.update({sid: "disabled" for sid in routing.disabled})

    plan = VideoCreativePlan(
        platform=platform, content_type=content_type, profile=routing.profile,
        story_arc=arc, emotional_arc=[b.emotion_to for b in arc],
        scene_directions=directions,
        pace_profile=("fast" if pacing.visual_refresh_flag == "TOO_FAST"
                      else "slow" if pacing.visual_refresh_flag == "TOO_SLOW" else "balanced"),
        visual_language={
            "edit_profile": edit_profile, "style": style,
            "shot_sizes": shot_plan.shot_size, "shot_purposes": shot_plan.shot_purpose,
            "visual_evidence_scenes": [d.scene_order for d in directions if d.visual_evidence],
        },
        editing_language={
            "visual_refresh_avg_s": pacing.visual_refresh_avg,
            "visual_refresh_flag": pacing.visual_refresh_flag,
            "cognitive_overload_scenes": pacing.overload_scenes,
            "effect_budget": pacing.effect_budget,
            "intents": pacing.edit_intent,
        },
        shot_language={
            "motion_energy": shot_plan.motion_energy,
            "cinematic_motion": shot_plan.cinematic_motion,
            "continuity_issues": shot_plan.issues,
        },
        voice_direction=voice,
        sound_direction=audio,
        caption_direction={
            "style": _caption_style_for(style, is_short),
            "kinetic_scenes": [d.scene_order for d in directions if d.kinetic_caption != "NONE"],
            "density": "high" if is_short else "moderate",
            "avoid_zones": ["face", "chart", "ui", "platform_safe_zones"],
        },
        color_direction={**_color.load_brand_colors(brand).to_dict(),
                         "match": "gentle-median", "max_adjust": 0.12},
        retention_strategy={
            "first_second_strength": retention.first_second_strength,
            "early_payoff": retention.early_payoff,
            "open_loops": retention.open_loops,
            "checkpoints": [vars(c) for c in retention.checkpoints],
            "pattern_interrupts": retention.pattern_interrupts,
        },
        budget_distribution=dist,
        high_impact_scenes=sorted(high_impact),
        boredom_risk=retention.boredom_risk,
        skills=skills,
        warnings=[w for w in warnings if w],
    )
    return plan


def _high_impact_scenes(directions, retention) -> set[int]:
    hi = {d.scene_order for d in directions
          if d.story_beat in ("HOOK", "SURPRISE", "PAYOFF", "PROOF")}
    if directions:
        hi.add(directions[0].scene_order)
        hi.add(directions[-1].scene_order)
    return hi


def _caption_style_for(style: str, is_short: bool) -> str:
    if not is_short:
        return "CLEAN"
    return {"NEWS": "TICKER", "DATA_DRIVEN": "PUNCH", "ENTERTAINMENT": "BOLD"}.get(
        style.upper(), "CLEAN")

