"""AUDIT-P8-002 — deterministic NL edit -> EditRequest + Smart-Rerender impact."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.db.base import session_scope
from app.db.models import Campaign, PlatformContent, Scene
from app.edit import apply_edit, impact_of, parse_instruction
from app.main import app

client = TestClient(app)


def _scenes():
    return [
        {"scene_order": 1, "still_asset_id": "a1", "voice_asset_id": "v1",
         "camera_motion": "SLOW_ZOOM_IN", "cinematic_motion": "", "estimated_duration": 4.0,
         "narration": "첫 장면"},
        {"scene_order": 2, "still_asset_id": "a2", "voice_asset_id": "v2",
         "camera_motion": "SLOW_ZOOM_IN", "cinematic_motion": "", "estimated_duration": 5.0,
         "narration": "둘째 장면"},
    ]


def test_parse_multi_clause_instruction():
    req = parse_instruction("2번 장면 자막을 더 크게 하고 그리고 배경음악을 잔잔하게")
    kinds = {(o.kind, o.params.get("style") or o.params.get("energy")) for o in req.ops}
    assert ("set_subtitle_style", "LARGE") in kinds
    assert ("change_music", "calm") in kinds


def test_scene_scoped_op_needs_scene_number():
    # no scene number -> the scene-scoped rule does not fire
    req = parse_instruction("장면 이미지를 바꿔줘")
    assert req.ops == [] and req.unmatched


def test_subtitle_only_change_reuses_ai_visuals():
    old = _scenes()
    req = parse_instruction("자막을 더 크게")
    new, meta = apply_edit(old, {"subtitle_blocks_hash": "h0", "music_style": "mid",
                                 "total_duration": 9.0}, req)
    imp = impact_of(old, new, old_meta={"subtitle_blocks_hash": "h0", "music_style": "mid",
                                        "total_duration": 9.0}, new_meta=meta)
    assert imp["rebuild_subtitles"] is True
    assert imp["regenerates_ai_visuals"] is False
    assert imp["rebuild_scene_clips"] == []
    assert imp["rebuild_composition"] is True


def test_broll_swap_regenerates_only_that_scene():
    old = _scenes()
    req = parse_instruction("2번 장면 b-roll을 교체해줘")
    new, meta = apply_edit(old, {}, req)
    imp = impact_of(old, new, old_meta={}, new_meta=meta)
    assert imp["rebuild_scene_clips"] == [2]
    assert imp["regenerates_ai_visuals"] is True


def test_edit_plan_endpoint():
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="t", audience_goal="BALANCED", platforms=["youtube_shorts"],
                        status="SUCCESS"))
        db.flush()
        pc = PlatformContent(campaign_id=cid, platform="youtube_shorts", content_type="short")
        db.add(pc)
        db.flush()
        for i in (1, 2, 3):
            db.add(Scene(campaign_id=cid, content_id=pc.id, scene_order=i,
                         estimated_duration=4.0, narration=f"n{i}", subtitle_text=f"s{i}",
                         camera_motion="SLOW_ZOOM_IN"))
    r = client.post(f"/api/library/{cid}/edit-plan",
                    json={"instruction": "전체를 조금 더 짧게"})
    assert r.status_code == 200
    body = r.json()
    assert body["request"]["ops"][0]["kind"] == "trim_all"
    assert body["impact"]["rebuild_composition"] is True
