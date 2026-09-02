from __future__ import annotations

import os

import pytest

from app.agents.media_runner import run_media_pipeline
from app.db.base import session_scope
from app.db.models import PlatformContent
from app.media.ffmpeg import probe

pytestmark = pytest.mark.integration


def test_creative_plan_and_video_qa_flow_through_media_pipeline(ready_campaign):
    cid = ready_campaign
    state = run_media_pipeline(cid, ["youtube_shorts"])

    assert state["status"] in ("SUCCESS", "FIX_REQUIRED")
    # existing guarantees still hold
    assert state["media_qa"]["passed"] is True

    # --- new: creative plan is present and sane -----------------------------
    cp = state.get("creative_plan") or {}
    assert "error" not in cp, cp
    assert cp["scene_directions"], "no scene directions produced"
    assert cp["scene_directions"][0]["story_beat"] == "HOOK"
    assert cp["story_arc"] and cp["retention_strategy"]["checkpoints"]
    assert cp["voice_direction"]["phrases"]
    assert cp["sound_direction"]["ducking"]
    assert set(cp["skills"].values()) <= {"required", "optional", "disabled"}
    assert 0.0 <= cp["boredom_risk"] <= 1.0

    # persisted on the content payload
    with session_scope() as s:
        content = s.query(PlatformContent).filter_by(
            campaign_id=cid, platform="youtube_shorts").first()
        assert (content.payload or {}).get("creative_plan")

    # --- new: video QA v2 -------------------------------------------------
    vqa = state.get("video_qa") or {}
    assert "error" not in vqa, vqa
    assert 0.0 <= vqa["overall"] <= 1.0
    assert len(vqa["dimensions"]) == 16
    assert "first_second_strength" in vqa

    # --- still a real rendered file ------------------------------------
    rp = state["render_path"]
    assert os.path.isfile(rp) and os.path.getsize(rp) > 100_000
    info = probe(rp)
    assert info["has_video"] and (info["width"], info["height"]) == (1080, 1920)


def test_cinematic_motion_renders_a_real_clip(tmp_path):
    """Direct render of one scene clip with a cinematic (parallax-sim) motion —
    proves the new motion path produces a valid mp4, not just a filter string."""
    import random as _r

    from PIL import Image

    from app.media.image_motion import render_scene_clip

    src = str(tmp_path / "still.png")
    # textured image so the encoder actually has detail to move (a flat colour
    # compresses to almost nothing and would not exercise the motion path)
    img = Image.new("RGB", (1080, 1920))
    rnd = _r.Random(7)
    img.putdata([(rnd.randint(0, 255), rnd.randint(40, 200), rnd.randint(20, 160))
                 for _ in range(1080 * 1920)])
    img.save(src)
    out = str(tmp_path / "clip.mp4")
    render_scene_clip(src, out, duration=2.0, width=1080, height=1920,
                      motion="DEPTH_PARALLAX_SIM")
    assert os.path.isfile(out) and os.path.getsize(out) > 20_000
    info = probe(out)
    assert info["has_video"] and (info["width"], info["height"]) == (1080, 1920)
    assert abs(info.get("duration", 0) - 2.0) < 0.6


def test_kinetic_ass_caption_writer(tmp_path):
    from app.media.subtitles import write_ass_kinetic
    from app.schemas.media import SubtitleBlock, WordTiming

    blocks = [SubtitleBlock(start=0.0, end=1.5, text="정말 놀라운 사실"),
              SubtitleBlock(start=1.5, end=3.0, text="지금 확인하세요")]
    wt = [WordTiming(word="정말", start=0.0, end=0.5),
          WordTiming(word="놀라운", start=0.5, end=1.0),
          WordTiming(word="사실", start=1.0, end=1.5)]
    p = str(tmp_path / "k.ass")
    write_ass_kinetic(blocks, p, play_w=1080, play_h=1920, word_timings=wt)
    txt = open(p, encoding="utf-8").read()
    assert "\\k" in txt and "Kinetic" in txt
    assert txt.count("Dialogue:") == 2
