from __future__ import annotations

import pytest

from app.video import director as _director
from app.video import audio_plan as _audio
from app.video import broll as _broll
from app.video import motion as _motion
from app.video import pacing as _pacing
from app.video import retention as _retention
from app.video import shots as _shots
from app.video import story as _story
from app.video import voice_plan as _voice
from app.video.router import route
from app.video.schema import SceneDirection

_SHORT_SCENES = [
    {"scene_order": 0, "narration": "왜 번역가라는 직업이 3년 만에 절반으로 줄었을까?", "estimated_duration": 3.2,
     "visual_type": "AI_IMAGE", "camera_motion": "SLOW_ZOOM_IN"},
    {"scene_order": 1, "narration": "먼저 사실부터. 통계에 따르면 수요가 20% 감소했다.", "estimated_duration": 4.5,
     "visual_type": "CHART", "camera_motion": "KEN_BURNS", "source_ids": ["s1"]},
    {"scene_order": 2, "narration": "하지만 반대로 돌봄 노동은 오히려 늘었다.", "estimated_duration": 4.0,
     "visual_type": "STOCK_VIDEO", "camera_motion": "PAN_RIGHT"},
    {"scene_order": 3, "narration": "놀랍게도 진짜 위험한 건 다른 직군이다.", "estimated_duration": 3.8,
     "visual_type": "AI_IMAGE", "camera_motion": "SLOW_ZOOM_IN"},
    {"scene_order": 4, "narration": "결론은 하나다. 지금 한 가지 업무를 자동화해보라.", "estimated_duration": 4.2,
     "visual_type": "TEXT_CARD", "camera_motion": "KEN_BURNS"},
    {"scene_order": 5, "narration": "다음 편에서 구체적 방법을 정리한다. 팔로우.", "estimated_duration": 3.0,
     "visual_type": "AI_IMAGE", "camera_motion": "PAN_LEFT"},
]


# ---- Story Director ------------------------------------------------------- #

def test_story_beats_have_hook_and_resolution():
    narrs = [s["narration"] for s in _SHORT_SCENES]
    beats, emos, arc = _story.build_story_arc(narrs)
    assert beats[0] == "HOOK"
    assert beats[-1] in ("CTA", "PAYOFF")
    assert "PAYOFF" in beats or "DISCOVERY" in beats
    assert len(emos) == len(narrs)
    # emotion cannot resolve to 'relief' before any tension/urgency/surprise
    for i, e in enumerate(emos):
        if e == "relief":
            assert any(x in ("tension", "urgency", "surprise") for x in emos[:i])


def test_story_proof_beat_on_numbers():
    beats = _story.assign_beats(["도입", "수치는 42% 상승했다", "마무리"])
    assert beats[1] == "PROOF"


# ---- Shot Grammar ------------------------------------------------------ #

def test_shot_grammar_breaks_scale_repetition():
    narrs = ["평범한 설명"] * 6
    beats = ["SETUP"] * 6
    emos = ["neutral"] * 6
    plan = _shots.plan_shots(narrs, beats, emos)
    assert len(plan.shot_size) == 6
    # a 6-long identical run must be broken
    assert any("SHOT_SCALE_REPETITION" in x for x in plan.issues)
    assert len(set(plan.shot_size)) >= 2


def test_camera_motion_continuity_flags_mechanical_alternation():
    issues = _shots.camera_motion_continuity(["A", "B", "A", "B", "A", "B"])
    assert any("MECHANICAL_ALTERNATION" in x for x in issues)
    issues2 = _shots.camera_motion_continuity(["A", "A", "A"])
    assert any("REPETITION" in x for x in issues2)


# ---- Retention Director ---------------------------------------------- #

def test_retention_detects_weak_hook_and_late_payoff():
    scenes = [
        {"scene_order": 0, "narration": "안녕하세요 여러분 오늘은 이 영상에서", "estimated_duration": 5},
        {"scene_order": 1, "narration": "계속 설명이 이어집니다", "estimated_duration": 5},
        {"scene_order": 2, "narration": "또 설명입니다", "estimated_duration": 5},
        {"scene_order": 3, "narration": "결론은 이것입니다", "estimated_duration": 5},
    ]
    dirs = [SceneDirection(scene_order=i, story_beat="SETUP") for i in range(4)]
    rep = _retention.analyze(scenes, dirs, is_short=True)
    assert rep.first_second_strength < 0.5
    assert any("first second" in n for n in rep.notes)
    assert rep.checkpoints and rep.checkpoints[0].label in ("0s", "1s", "intro")


def test_boredom_scan_flags_flat_sequence():
    scenes = [{"scene_order": i, "narration": "설명", "estimated_duration": 4,
               "visual_type": "AI_IMAGE", "camera_motion": "SLOW_ZOOM_IN"} for i in range(7)]
    dirs = [SceneDirection(scene_order=i, shot_size="MEDIUM", motion_energy="MEDIUM",
                           primary_focus="scene") for i in range(7)]
    risk, spans, _ = _retention.boredom_scan(scenes, dirs)
    assert risk >= 0.5 and spans


# ---- Pacing ---------------------------------------------------------- #

def test_pacing_cognitive_overload_detected():
    scenes = [{
        "scene_order": 0, "narration": "무려 12% 상승, 34% 하락, 그리고 56% 유지라는 3개의 수치가 동시에",
        "estimated_duration": 2.0, "visual_type": "CHART", "subtitle_text": "다른 자막 텍스트",
        "sound_effect": "whoosh",
    }]
    dirs = [SceneDirection(scene_order=0, motion_energy="HIGH")]
    rep = _pacing.analyze(scenes, dirs, content_kind="SHORTS")
    assert rep.cognitive_load[0] >= 0.6
    assert 0 in rep.overload_scenes


def test_pacing_visual_refresh_flag():
    fast = [{"scene_order": i, "narration": "x", "estimated_duration": 0.8,
             "visual_type": f"T{i}", "camera_motion": f"M{i}"} for i in range(8)]
    avg, flag = _pacing.visual_refresh(fast, [], "SHORTS")
    assert flag == "TOO_FAST"


# ---- B-roll Director ----------------------------------------------- #

def test_broll_kind_classification_and_license_gate():
    scene = {"narration": "경쟁이 빠르게 심화되고 있다"}
    direct = _broll.BrollCandidate(ref="c1", description="사람들이 사무실에서 경쟁 회의",
                                   tags=["office", "competition"])
    meta = _broll.BrollCandidate(ref="c2", description="질주하는 육상 선수 트랙 레이스",
                                 tags=["running", "race"])
    bad = _broll.BrollCandidate(ref="c3", description="질주하는 사람", license_ok=False)
    r = _broll.rank(scene, [direct, meta, bad], beat="HOOK", emotion="urgency")
    refs = [x.ref for x in r]
    assert refs[-1] == "c3"                      # unlicensed sinks to the bottom
    assert r[refs.index("c3") if "c3" in refs else -1].total == 0.0
    assert {"DIRECT", "METAPHORICAL", "CONTEXTUAL"} & {x.kind for x in r}


def test_broll_visual_evidence_priority():
    assert _broll.visual_evidence_priority({"narration": "조사에 따르면 42%가 그렇다"}) is True
    assert _broll.visual_evidence_priority({"narration": "그냥 분위기 있는 장면"}) is False


# ---- Cinematic motion (filter strings) --------------------------- #

@pytest.mark.parametrize("m", ["DEPTH_PARALLAX_SIM", "DOLLY_IN_SIM", "FOCUS_PULL_SIM",
                               "SLOW_ORBIT_SIM", "KEN_BURNS", "SLOW_ZOOM_IN"])
def test_cinematic_motion_builds_valid_zoompan(m):
    vf = _motion.zoompan_expr(m, frames=90, w=1080, h=1920, fps=30)
    assert "zoompan=" in vf and "s=1080x1920" in vf and "fps=30" in vf
    assert vf.count("'") % 2 == 0                # balanced quotes
    if m == "FOCUS_PULL_SIM":
        assert "boxblur" in vf


# ---- Voice Director V2 ------------------------------------------- #

def test_voice_plan_stays_in_brand_band():
    dirs = [SceneDirection(scene_order=i, story_beat=b) for i, b in
            enumerate(["HOOK", "PROOF", "CONTRAST", "PAYOFF"])]
    scenes = [{"scene_order": i, "narration": s["narration"]}
              for i, s in enumerate(_SHORT_SCENES[:4])]
    vp = _voice.plan_voice(scenes, dirs)
    speeds = [p.speed for p in vp.phrases]
    assert all(0.9 <= s <= 1.12 for s in speeds)
    assert 0.0 <= vp.consistency_score <= 1.0
    # a plan with wild swings scores low
    from app.video.schema import VoicePhrasePlan
    wild = [VoicePhrasePlan(scene_order=0, text="a", speed=0.9),
            VoicePhrasePlan(scene_order=0, text="b", speed=1.3),
            VoicePhrasePlan(scene_order=0, text="c", speed=0.85),
            VoicePhrasePlan(scene_order=0, text="d", speed=1.25)]
    sc, notes = _voice.consistency_score(wild)
    assert sc < 0.8 and notes


# ---- Audio Director ------------------------------------------- #

def test_audio_ducking_envelope_is_smooth_and_music_structured():
    scenes = [{"scene_order": i, "narration": "말", "estimated_duration": 4.0} for i in range(5)]
    ap = _audio.plan_audio(scenes, ["HOOK", "SETUP", "PROOF", "PAYOFF", "CTA"])
    assert [m.label for m in ap.music_sections] == ["intro", "build", "drop", "break", "outro"]
    assert ap.ducking and ap.ducking[0].t == 0.0
    # keyframes strictly non-decreasing in time
    ts = [k.t for k in ap.ducking]
    assert ts == sorted(ts)
    # energy follows the arc, not flat
    assert max(ap.energy_curve) - min(ap.energy_curve) >= 0.2


def test_audio_sfx_density_flag():
    scenes = [{"scene_order": i, "narration": "x", "estimated_duration": 1.0,
               "sound_effect": "boom"} for i in range(10)]
    dens, flag = _audio.sfx_density(scenes, 10.0)
    assert flag == "HIGH"


# ---- Router ------------------------------------------------- #

def test_router_gates_gpu_skills_without_gpu():
    r = route(platform="youtube_shorts", content_type="SHORT_VIDEO", profile="CINEMATIC",
              budget_usd=5.0, gpu_available=False)
    assert "segmentation_sam2" in r.optional
    assert "segmentation_sam2" in r.fallbacks
    assert "story_director_v1" in r.required
    r2 = route(platform="youtube_shorts", content_type="SHORT_VIDEO", profile="FAST",
               budget_usd=0.2)
    assert "broll_ranker_v1" not in r2.required           # FAST profile is lean
    assert "diarization_v1" in r2.disabled                # single speaker default


def test_router_diarization_enabled_for_multispeaker():
    r = route(platform="youtube_long", content_type="EXPLAINER", profile="PREMIUM",
              budget_usd=3.0, multi_speaker=True)
    assert "diarization_v1" not in r.disabled


# ---- VideoDirector end-to-end (deterministic) ------------- #

def test_video_director_produces_full_plan():
    plan = _director.direct_video(platform="youtube_shorts", content_type="SHORT_VIDEO",
                                  scenes=_SHORT_SCENES, profile="PREMIUM")
    assert plan.story_arc and plan.scene_directions
    assert len(plan.scene_directions) == len(_SHORT_SCENES)
    assert plan.scene_directions[0].story_beat == "HOOK"
    assert plan.high_impact_scenes and 0 in plan.high_impact_scenes
    assert abs(sum(plan.budget_distribution.values()) - 1.0) < 0.01  # 4dp rounding
    assert plan.voice_direction.phrases
    assert plan.sound_direction.ducking
    assert set(plan.skills.values()) <= {"required", "optional", "disabled"}
    d = plan.to_dict()
    assert d["platform"] == "youtube_shorts" and d["profile"] == "PREMIUM"
    assert "retention_strategy" in d and "checkpoints" in d["retention_strategy"]


def test_video_director_is_deterministic():
    a = _director.direct_video(platform="youtube_shorts", content_type="SHORT_VIDEO",
                               scenes=_SHORT_SCENES).to_dict()
    b = _director.direct_video(platform="youtube_shorts", content_type="SHORT_VIDEO",
                               scenes=_SHORT_SCENES).to_dict()
    assert a == b


def test_adapters_never_fake_results():
    from app.video.adapters import OptionalSkillUnavailable
    from app.video.adapters import models

    with pytest.raises(OptionalSkillUnavailable):
        models.segment_subject("x.png")
    with pytest.raises(OptionalSkillUnavailable):
        models.depth_map("x.png", model_size="giant")   # blocked: non-commercial weights
    # deterministic reframe fallback always works
    from app.video.adapters.reframe import safe_reframe_box
    box = safe_reframe_box(1920, 1080, 9 / 16, focus_hint="speaker")
    assert 0 <= box.x <= 1 and 0 < box.w <= 1 and box.method == "rule_of_thirds_safe"
