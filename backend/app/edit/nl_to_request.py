"""AUDIT-P8-002 — deterministic natural-language edit request + impact preview.

`parse_instruction("2번 장면 자막을 더 크게 하고 배경음악을 잔잔하게")` ->
    EditRequest(ops=[EditOp("set_subtitle_style", {"scene": 2, "style": "LARGE"}),
                     EditOp("change_music", {"energy": "calm"})])

No LLM: a small phrase table maps intent + an optional scene number to a typed op.
`apply_edit` produces the new scene list / meta, and `impact_of` runs the existing
Smart-Rerender planner so the UI can show "this change re-runs X" BEFORE applying.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.video.rerender import plan_rerender

# ---- phrase table (Korean + English), longest / most specific first ---- #
# each entry: (compiled pattern, op_kind, static params, needs_scene)
_RULES: list[tuple[re.Pattern, str, dict, bool]] = []


def _r(pattern: str, kind: str, params: dict, needs_scene: bool = False) -> None:
    _RULES.append((re.compile(pattern, re.I), kind, params, needs_scene))


# subtitles
_r(r"자막.*(키우|크게|더 크)", "set_subtitle_style", {"style": "LARGE"})
_r(r"자막.*(줄이|작게)", "set_subtitle_style", {"style": "SMALL"})
_r(r"자막.*(강조|하이라이트)", "set_subtitle_style", {"style": "HIGHLIGHT"})
_r(r"(bigger|larger).*(caption|subtitle)|caption.*bigger", "set_subtitle_style", {"style": "LARGE"})
_r(r"자막.*(빼|제거|없)", "toggle_subtitles", {"on": False})
# music
_r(r"(배경\s*음악|bgm|music).*(잔잔|차분|조용|calm|soft|quiet)", "change_music", {"energy": "calm"})
_r(r"(배경\s*음악|bgm|music).*(신나|고조|강하|energetic|upbeat|hype)", "change_music", {"energy": "high"})
_r(r"(음악|music).*(빼|제거|없|remove|no music)", "change_music", {"energy": "none"})
# pacing / duration
_r(r"(장면|씬|scene).*(짧게|줄여|trim|shorten|빠르게)", "trim_scene", {"delta": -1.0}, True)
_r(r"(장면|씬|scene).*(길게|늘려|extend|longer|천천)", "extend_scene", {"delta": 1.0}, True)
_r(r"(전체|영상).*(짧게|줄여|빠르게|faster|shorten)", "trim_all", {"factor": 0.9})
# visuals / b-roll
_r(r"(b-?roll|비롤|배경\s*영상|영상 클립).*(바꿔|교체|다르게|replace|swap|change)",
   "replace_broll", {}, True)
_r(r"(장면|씬|scene).*(이미지|비주얼|visual|image).*(바꿔|교체|replace|change)",
   "replace_broll", {}, True)
_r(r"(차트|그래프|데이터 시각).*(넣|추가|add chart|add graphic)", "add_graphic",
   {"kind": "chart"}, True)
# camera motion
_r(r"(카메라|모션|motion|zoom).*(빼|없|정지|still|static|no motion)", "set_camera_motion",
   {"motion": "NONE"}, True)
_r(r"(카메라|모션|motion).*(줌|zoom|push)", "set_camera_motion", {"motion": "SLOW_ZOOM_IN"}, True)
# narration / hook
_r(r"(훅|hook|도입|첫 ?문장).*(바꿔|다시|새로|rewrite|change)", "rewrite_hook", {})
_r(r"(내레이션|나레이션|narration|대사).*(장면|씬|scene).*(바꿔|수정|rewrite|change)",
   "rewrite_narration", {}, True)

_SCENE_RE = re.compile(r"(\d+)\s*(?:번|번째|scene|씬|장면)", re.I)


@dataclass
class EditOp:
    kind: str
    params: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "params": self.params}


@dataclass
class EditRequest:
    ops: list[EditOp] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ops": [o.as_dict() for o in self.ops], "unmatched": self.unmatched}


def _scene_num(fragment: str, whole: str) -> int | None:
    m = _SCENE_RE.search(fragment) or _SCENE_RE.search(whole)
    return int(m.group(1)) if m else None


def parse_instruction(text: str) -> EditRequest:
    """Split on ' 그리고 ' / ',' / ' and ' and match each clause to one op."""
    text = (text or "").strip()
    if not text:
        return EditRequest()
    clauses = [c.strip() for c in re.split(r"\s*(?:그리고|,|·|and)\s+", text) if c.strip()]
    req = EditRequest()
    seen: set[tuple] = set()
    for clause in clauses or [text]:
        matched = False
        for pat, kind, params, needs_scene in _RULES:
            if not pat.search(clause):
                continue
            p = dict(params)
            if needs_scene:
                sn = _scene_num(clause, text)
                if sn is None:
                    continue  # scene-scoped op needs a scene number
                p["scene"] = sn
            key = (kind, tuple(sorted(p.items())))
            if key in seen:
                matched = True
                break
            seen.add(key)
            req.ops.append(EditOp(kind, p))
            matched = True
            break
        if not matched:
            req.unmatched.append(clause)
    return req


# ---- apply -------------------------------------------------------------- #

_MUSIC_STYLE = {"calm": "calm_minimal", "high": "energetic", "none": ""}


def apply_edit(scenes: list[dict], meta: dict, request: EditRequest) -> tuple[list[dict], dict]:
    """Pure function: return NEW scenes + meta. Never mutates the inputs."""
    new = [dict(s) for s in scenes]
    m = dict(meta or {})
    by_order = {int(s.get("scene_order", i)): s for i, s in enumerate(new)}

    for op in request.ops:
        p = op.params
        sc = by_order.get(int(p["scene"])) if "scene" in p else None
        if op.kind == "set_subtitle_style":
            m["subtitle_style"] = p["style"]
            m["subtitle_blocks_hash"] = f"{m.get('subtitle_blocks_hash', '')}|style={p['style']}"
        elif op.kind == "toggle_subtitles":
            m["subtitles_on"] = p["on"]
            m["subtitle_blocks_hash"] = f"{m.get('subtitle_blocks_hash', '')}|on={p['on']}"
        elif op.kind == "change_music":
            m["music_style"] = _MUSIC_STYLE.get(p["energy"], m.get("music_style", ""))
        elif op.kind == "trim_all":
            for s in new:
                s["estimated_duration"] = round(float(s.get("estimated_duration", 0)) * p["factor"], 2)
            m["total_duration"] = round(sum(float(s.get("estimated_duration", 0)) for s in new), 1)
        elif sc is not None and op.kind in ("trim_scene", "extend_scene"):
            sc["estimated_duration"] = max(
                0.5, round(float(sc.get("estimated_duration", 0)) + p["delta"], 2))
            m["total_duration"] = round(sum(float(s.get("estimated_duration", 0)) for s in new), 1)
        elif sc is not None and op.kind == "replace_broll":
            sc["still_asset_id"] = None
            sc["visual_prompt_rev"] = int(sc.get("visual_prompt_rev", 0)) + 1
        elif sc is not None and op.kind == "add_graphic":
            sc["graphic"] = p["kind"]
            sc["visual_prompt_rev"] = int(sc.get("visual_prompt_rev", 0)) + 1
        elif sc is not None and op.kind == "set_camera_motion":
            sc["camera_motion"] = p["motion"]
        elif sc is not None and op.kind == "rewrite_narration":
            sc["narration"] = f"{sc.get('narration', '')} [rewrite-requested]"
        elif op.kind == "rewrite_hook" and new:
            first = by_order.get(min(by_order))
            if first is not None:
                first["narration"] = f"{first.get('narration', '')} [hook-rewrite-requested]"
    return new, m


# ---- impact ----------------------------------------------------------- #

def impact_of(old_scenes: list[dict], new_scenes: list[dict], *,
              old_meta: dict | None = None, new_meta: dict | None = None) -> dict:
    """Human-readable "this change will re-run X" from the Smart-Rerender planner."""
    plan = plan_rerender(old_scenes, new_scenes, old_meta=old_meta, new_meta=new_meta)
    steps: list[str] = []
    if plan.rebuild_scene_clips:
        steps.append(f"{len(plan.rebuild_scene_clips)}개 장면 클립 재생성 "
                     f"(scene {plan.rebuild_scene_clips})")
    if plan.rebuild_voice:
        steps.append(f"{len(plan.rebuild_voice)}개 장면 나레이션 재합성")
    if plan.rebuild_subtitles:
        steps.append("자막 재생성 (AI 이미지/영상은 재사용)")
    if plan.rebuild_music:
        steps.append("배경음악 재생성")
    if plan.rebuild_composition:
        steps.append("최종 컴포지션 재렌더")
    return {
        "noop": plan.is_noop,
        "rebuild_scene_clips": plan.rebuild_scene_clips,
        "rebuild_voice": plan.rebuild_voice,
        "rebuild_subtitles": plan.rebuild_subtitles,
        "rebuild_music": plan.rebuild_music,
        "rebuild_composition": plan.rebuild_composition,
        "reused": plan.reused,
        "reused_count": len(plan.reused),
        "human_steps": steps or ["변경 없음"],
        "regenerates_ai_visuals": bool(plan.rebuild_scene_clips),
    }
