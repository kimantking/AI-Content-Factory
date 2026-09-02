"""Smart Rerender dependency graph (B43, B92).

Given the previous render's per-scene input hashes and the new ones, decide the
minimal set of scene clips + composition steps to re-render. A subtitle-only
change must NOT trigger AI image/video regeneration.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

# what each render stage depends on
_STAGE_DEPS = {
    "scene_clip": ("still_asset_id", "camera_motion", "cinematic_motion", "estimated_duration"),
    "voice": ("voice_asset_id", "narration"),
    "subtitles": ("subtitle_blocks_hash",),
    "music": ("music_style", "total_duration"),
    "composition": ("scene_clip", "voice", "subtitles", "music"),
}


def scene_hash(scene: dict, keys: tuple[str, ...]) -> str:
    payload = {k: scene.get(k) for k in keys}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()[:16]


@dataclass
class RerenderPlan:
    rebuild_scene_clips: list[int] = field(default_factory=list)
    rebuild_voice: list[int] = field(default_factory=list)
    rebuild_subtitles: bool = False
    rebuild_music: bool = False
    rebuild_composition: bool = False
    reused: list[str] = field(default_factory=list)

    @property
    def is_noop(self) -> bool:
        return not (self.rebuild_scene_clips or self.rebuild_voice or self.rebuild_subtitles
                    or self.rebuild_music or self.rebuild_composition)


def plan_rerender(old_scenes: list[dict], new_scenes: list[dict], *,
                  old_meta: dict | None = None, new_meta: dict | None = None) -> RerenderPlan:
    old_meta = old_meta or {}
    new_meta = new_meta or {}
    old_by = {int(s.get("scene_order", i)): s for i, s in enumerate(old_scenes)}
    plan = RerenderPlan()

    for i, s in enumerate(new_scenes):
        so = int(s.get("scene_order", i))
        old = old_by.get(so)
        if old is None:
            plan.rebuild_scene_clips.append(so)
            plan.rebuild_voice.append(so)
            continue
        if scene_hash(s, _STAGE_DEPS["scene_clip"]) != scene_hash(old, _STAGE_DEPS["scene_clip"]):
            plan.rebuild_scene_clips.append(so)
        else:
            plan.reused.append(f"scene_clip:{so}")
        if scene_hash(s, _STAGE_DEPS["voice"]) != scene_hash(old, _STAGE_DEPS["voice"]):
            plan.rebuild_voice.append(so)
        else:
            plan.reused.append(f"voice:{so}")

    if old_meta.get("subtitle_blocks_hash") != new_meta.get("subtitle_blocks_hash"):
        plan.rebuild_subtitles = True
    else:
        plan.reused.append("subtitles")
    if (old_meta.get("music_style"), round(old_meta.get("total_duration", 0), 1)) != \
       (new_meta.get("music_style"), round(new_meta.get("total_duration", 0), 1)):
        plan.rebuild_music = True
    else:
        plan.reused.append("music")

    plan.rebuild_composition = bool(
        plan.rebuild_scene_clips or plan.rebuild_voice or plan.rebuild_subtitles or plan.rebuild_music
    )
    return plan
