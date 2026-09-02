#!/usr/bin/env python3
"""Generate real advanced test videos (Video Studio Upgrade B110-B112).

Builds two campaigns through Phase 1-A -> the media pipeline (which now runs the
deterministic Video Director), copies the renders to outputs/, and runs ffprobe +
media QA + Video QA v2 + real ffmpeg loudness/colour probes on each. No empty
mock MP4s — these go through the full renderer.

Usage:  backend/.venv/Scripts/python.exe backend/scripts/video/make_advanced_samples.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.agents.media_runner import run_media_pipeline  # noqa: E402
from app.agents.runner import run_pipeline  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.base import session_scope  # noqa: E402
from app.db.models import Campaign  # noqa: E402
from app.media.ffmpeg import probe  # noqa: E402
from app.video import ffmpeg_probe as vprobe  # noqa: E402

CASES = [
    # TEST A — 60s information short
    ("advanced_short", "AI로 사라질 가능성이 높은 직업", "VIEWS", ["youtube_shorts"]),
    # TEST B — fast trend short (30-45s target)
    ("advanced_trend_short", "이번 주 갑자기 화제가 된 신기술 한 가지", "VIEWS", ["tiktok"]),
    # TEST C — 3-5min explainer
    ("advanced_explainer", "재택근무가 도시 부동산에 미치는 진짜 영향", "BALANCED", ["youtube_long"]),
]


def _run_case(name: str, topic: str, goal: str, platforms: list[str]) -> dict:
    cid = str(uuid.uuid4())
    with session_scope() as s:
        s.add(Campaign(id=cid, topic=topic, audience_goal=goal, platforms=platforms, status="WAITING"))
    run_pipeline(cid, topic, goal, platforms)
    with session_scope() as s:
        assert s.get(Campaign, cid).status == "SUCCESS", "phase 1-A failed"
    state = run_media_pipeline(cid, platforms)

    rp = state.get("render_path")
    if not rp or not os.path.isfile(rp):
        return {"name": name, "ok": False, "error": "no render produced"}

    out_dir = Path(get_settings().output_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{name}.mp4"
    shutil.copyfile(rp, dst)

    info = probe(str(dst))
    loud = vprobe.check_loudness(str(dst), target_lufs=state.get("creative_plan", {})
                                 .get("sound_direction", {}).get("loudness_target_lufs", -14.0))
    color = vprobe.color_stats(str(dst))
    freeze = vprobe.freeze_frames(str(dst))
    sync = vprobe.av_sync_drift(str(dst))
    cp = state.get("creative_plan", {})
    vqa = state.get("video_qa", {})
    return {
        "name": name, "ok": True, "path": str(dst), "bytes": os.path.getsize(dst),
        "probe": {k: info.get(k) for k in ("has_video", "has_audio", "width", "height", "duration", "fps")},
        "media_qa_passed": state["media_qa"]["passed"],
        "content_qa_overall": state["content_qa"]["overall"],
        "video_qa": {"overall": vqa.get("overall"), "passed": vqa.get("passed"),
                     "weak": vqa.get("weak"), "boredom_risk": vqa.get("boredom_risk"),
                     "first_second_strength": vqa.get("first_second_strength"),
                     "bad_scenes": vqa.get("bad_scenes")},
        "creative_plan": {
            "profile": cp.get("profile"),
            "story_arc": [b["beat"] for b in cp.get("story_arc", [])],
            "emotional_arc": cp.get("emotional_arc"),
            "pace_profile": cp.get("pace_profile"),
            "visual_refresh": cp.get("editing_language", {}).get("visual_refresh_avg_s"),
            "high_impact_scenes": cp.get("high_impact_scenes"),
            "skills_required": [k for k, v in cp.get("skills", {}).items() if v == "required"],
            "warnings": cp.get("warnings"),
        },
        "loudness": loud, "color_stats": color,
        "freeze_frames": freeze, "av_sync": sync,
    }


def main() -> int:
    results = [_run_case(*c) for c in CASES]
    report = Path(get_settings().output_root) / "advanced_samples_report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    # ascii-safe stdout (Windows consoles are often cp949)
    print(json.dumps(results, ensure_ascii=True, indent=2))
    print(f"\nreport written to {report}")
    ok = all(r.get("ok") and r["probe"]["has_video"] for r in results)
    print("ADVANCED SAMPLES:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
