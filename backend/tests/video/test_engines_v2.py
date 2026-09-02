from __future__ import annotations

from app.video import captions as cap
from app.video import creative_qa as cq
from app.video import cuts as cu
from app.video import quality as ql
from app.video import rerender as rr
from app.video import voice_plan as vp
from app.video.schema import SceneDirection

_SCENES = [
    {"scene_order": 0, "narration": "왜 이 직업이 사라질까? 지금 확인하세요!", "estimated_duration": 3.5,
     "visual_type": "AI_IMAGE", "camera_motion": "SLOW_ZOOM_IN"},
    {"scene_order": 1, "narration": "통계에 따르면 수요가 20% 줄었다", "estimated_duration": 4.5,
     "visual_type": "CHART", "camera_motion": "KEN_BURNS"},
    {"scene_order": 2, "narration": "놀랍게도 다른 직군이 더 위험하다", "estimated_duration": 4.0,
     "visual_type": "STOCK_VIDEO", "camera_motion": "PAN_RIGHT"},
    {"scene_order": 3, "narration": "결론은 하나다. 한 가지를 자동화하라", "estimated_duration": 4.0,
     "visual_type": "TEXT_CARD", "camera_motion": "SLOW_ZOOM_IN"},
]
_DIRS = [SceneDirection(scene_order=i, story_beat=b, motion_energy="MEDIUM",
                        cinematic_motion="KEN_BURNS", effect_budget=2)
         for i, b in enumerate(["HOOK", "PROOF", "SURPRISE", "PAYOFF"])]


# ---- Cut Engine V2 -------------------------------------------------------- #

def test_cut_engine_scores_scene_boundaries_hard_and_finds_soft_points():
    cuts = cu.score_cuts(_SCENES, _DIRS)
    hard = [c for c in cuts if c.kind == "HARD"]
    soft = [c for c in cuts if c.kind == "SOFT"]
    assert len(hard) == len(_SCENES)
    assert soft and any("emphasis" in c.reasons or "reaction" in c.reasons for c in soft)
    # story-beat change is a reason on at least one hard cut
    assert any(any("story_beat_change" in r for r in c.reasons) for c in hard)
    rep = cu.cut_rhythm_report(cuts)
    assert rep["n"] == len(cuts) and rep["flag"] in ("OK", "MECHANICAL")


def test_cut_engine_flags_mechanical_fixed_interval():
    scenes = [{"scene_order": i, "narration": "설명", "estimated_duration": 4.0,
               "visual_type": "AI_IMAGE", "camera_motion": "SLOW_ZOOM_IN"} for i in range(6)]
    dirs = [SceneDirection(scene_order=i, story_beat="SETUP") for i in range(6)]
    cuts = cu.score_cuts(scenes, dirs)
    rep = cu.cut_rhythm_report([c for c in cuts if c.kind == "HARD"])
    assert rep["flag"] == "MECHANICAL"


# ---- Caption collision -------------------------------------------------- #

def test_caption_avoids_face_zone():
    p = cap.resolve_placement("이건 정말 중요합니다", ["face", "platform_safe_zones"])
    assert p.band in ("lower_third", "lower_mid")
    assert "face" not in p.collided_with


def test_caption_emphasis_is_selective():
    e = cap.emphasis_words("무려 42% 가 놀랍게도 사라진다")
    assert "42%" in e and len(e) <= 2


def test_caption_reading_speed():
    ok, cps = cap.caption_load_ok("짧은 자막", 2.0)
    assert ok
    bad_ok, bad_cps = cap.caption_load_ok("아주 긴 자막이 짧은 시간에 화면을 가득 채우면 읽을 수 없습니다 정말로", 1.0)
    assert not bad_ok and bad_cps > 17


# ---- Creative QA V2 -------------------------------------------------- #

def test_creative_qa_flags_ai_overuse_and_repetitive_zoom():
    scenes = [{"scene_order": i, "narration": "x", "visual_type": "AI_IMAGE",
               "camera_motion": "SLOW_ZOOM_IN", "estimated_duration": 4} for i in range(6)]
    dirs = [SceneDirection(scene_order=i, story_beat="SETUP") for i in range(6)]
    rep = cq.evaluate(scenes, dirs, music_style="AMBIENT")
    assert rep.checks["ai_visual_overuse"] == "FAIL"
    assert rep.checks["repetitive_zoom"] == "FAIL"
    assert rep.checks["weak_story_arc"] == "FAIL"
    assert rep.checks["generic_music"] == "WARN"
    assert rep.passed is False


def test_creative_qa_passes_varied_video():
    rep = cq.evaluate(_SCENES, _DIRS, music_style="TENSE_ELECTRONIC")
    assert rep.checks["weak_story_arc"] == "OK"
    assert rep.passed is True


# ---- Smart Rerender --------------------------------------------------- #

def test_rerender_subtitle_only_change_does_not_rebuild_clips():
    old = [{"scene_order": i, "still_asset_id": f"a{i}", "camera_motion": "KEN_BURNS",
            "cinematic_motion": "KEN_BURNS", "estimated_duration": 4.0,
            "voice_asset_id": f"v{i}", "narration": f"n{i}"} for i in range(3)]
    new = [dict(s) for s in old]
    plan = rr.plan_rerender(old, new,
                            old_meta={"subtitle_blocks_hash": "aaa", "music_style": "X", "total_duration": 12.0},
                            new_meta={"subtitle_blocks_hash": "bbb", "music_style": "X", "total_duration": 12.0})
    assert plan.rebuild_scene_clips == [] and plan.rebuild_voice == []
    assert plan.rebuild_subtitles is True
    assert plan.rebuild_music is False
    assert plan.rebuild_composition is True


def test_rerender_noop_when_nothing_changed():
    old = [{"scene_order": 0, "still_asset_id": "a", "camera_motion": "KEN_BURNS",
            "cinematic_motion": "KEN_BURNS", "estimated_duration": 4.0,
            "voice_asset_id": "v", "narration": "n"}]
    plan = rr.plan_rerender(old, [dict(old[0])],
                            old_meta={"subtitle_blocks_hash": "h", "music_style": "X", "total_duration": 4.0},
                            new_meta={"subtitle_blocks_hash": "h", "music_style": "X", "total_duration": 4.0})
    assert plan.is_noop


def test_rerender_broll_change_rebuilds_one_scene_and_composition():
    old = [{"scene_order": i, "still_asset_id": f"a{i}", "camera_motion": "KEN_BURNS",
            "cinematic_motion": "KEN_BURNS", "estimated_duration": 4.0,
            "voice_asset_id": f"v{i}", "narration": f"n{i}"} for i in range(3)]
    new = [dict(s) for s in old]
    new[1]["still_asset_id"] = "NEW"
    plan = rr.plan_rerender(old, new,
                            old_meta={"subtitle_blocks_hash": "h", "music_style": "X", "total_duration": 12.0},
                            new_meta={"subtitle_blocks_hash": "h", "music_style": "X", "total_duration": 12.0})
    assert plan.rebuild_scene_clips == [1] and plan.rebuild_voice == []
    assert plan.rebuild_composition is True


# ---- Voice pause classification ----------------------------------- #

def test_pause_classification():
    assert vp.classify_pause(0.5, at_sentence_end=False, before_emphasis=True, at_beat_change=False) == "DRAMATIC"
    assert vp.classify_pause(0.2, at_sentence_end=True, before_emphasis=False, at_beat_change=False) == "BREATH"
    assert vp.classify_pause(0.08, at_sentence_end=False, before_emphasis=False, at_beat_change=False) == "UNNECESSARY"
    assert vp.classify_pause(0.02, at_sentence_end=False, before_emphasis=False, at_beat_change=False) == "NONE"


def test_plan_voice_annotates_pause_kinds():
    scenes = [{"scene_order": i, "narration": s["narration"]} for i, s in enumerate(_SCENES)]
    plan = vp.plan_voice(scenes, _DIRS)
    kinds = {p.pause_after_kind for p in plan.phrases}
    assert kinds and kinds <= {"NONE", "BREATH", "EMPHASIS", "DRAMATIC", "UNNECESSARY"}


# ---- Quality extensions ------------------------------------------ #

def test_quality_score_100_and_repair_plan():
    from app.video import shots as _shots, story as _story, retention as _ret, audio_plan as _ap

    narrs = [s["narration"] for s in _SCENES]
    beats, emos, arc = _story.build_story_arc(narrs)
    sp = _shots.plan_shots(narrs, beats, emos)
    ret = _ret.analyze(_SCENES, _DIRS, is_short=True)

    class _SR:
        story_arc = arc
    vs = ql.score(story_report=_SR(), retention_report=ret,
                  pacing_report=type("P", (), {"visual_refresh_flag": "OK"})(),
                  shot_plan=sp, voice_plan=vp.plan_voice(
                      [{"scene_order": i, "narration": n} for i, n in enumerate(narrs)], _DIRS),
                  audio_plan=_ap.plan_audio(_SCENES, beats),
                  content_qa={"scores": {}}, media_qa={"passed": True})
    s100 = ql.score_100(vs)
    assert 0 <= s100["overall"] <= 100 and len(s100["dimensions"]) == 16

    bad = ql.detect_bad_scenes(
        [{"scene_order": i, "narration": "x", "visual_type": "AI_IMAGE",
          "camera_motion": "SLOW_ZOOM_IN", "estimated_duration": 4} for i in range(6)],
        [SceneDirection(scene_order=i, story_beat="SETUP") for i in range(6)])
    repairs = ql.plan_repairs(bad)
    assert repairs and all("strategy" in r for r in repairs) and len(repairs) <= 4
    assert 0.0 <= ql.continuity_score(sp) <= 1.0
