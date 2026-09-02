"""Editor Memory (B105): remember the last few videos' stylistic choices so the
next one doesn't repeat them. Backed by the existing LearningMemory table
(memory_type='VISUAL', dimension='editor_style') — no new schema.
"""
from __future__ import annotations

from collections import Counter

_KEYS = ("cinematic_motions", "shot_sizes", "caption_style", "transition",
         "music_style", "thumbnail_layout", "visual_types")


def snapshot_from_plan(plan) -> dict:
    """Extract a compact style fingerprint from a VideoCreativePlan."""
    dirs = getattr(plan, "scene_directions", [])
    return {
        "cinematic_motions": Counter(d.cinematic_motion for d in dirs).most_common(3),
        "shot_sizes": Counter(d.shot_size for d in dirs).most_common(3),
        "caption_style": (getattr(plan, "caption_direction", {}) or {}).get("style", "CLEAN"),
        "music_style": (getattr(plan, "sound_direction", None).music_sections[0].label
                        if getattr(plan, "sound_direction", None) and plan.sound_direction.music_sections
                        else "ambient"),
        "visual_types": [],
    }


def record(session, *, brand: str | None, plan) -> None:
    from app.learning.memory import upsert_memory

    snap = snapshot_from_plan(plan)
    upsert_memory(
        session, memory_type="VISUAL", dimension="editor_style",
        topic_cluster=None, platform=getattr(plan, "platform", None),
        statement=f"recent edit style: motions={snap['cinematic_motions']}, "
                  f"shots={snap['shot_sizes']}, captions={snap['caption_style']}",
        recommendation={"kind": "EDITOR_STYLE_RECENT", **{k: str(v) for k, v in snap.items()}},
        confidence=0.5, sample_size=1, consistent=True,
    )


def recent_style(session, *, platform: str | None = None, limit: int = 5) -> dict:
    """Aggregate the last few EDITOR_STYLE_RECENT memories into 'avoid' hints."""
    from app.db.models import LearningMemory

    q = (session.query(LearningMemory)
         .filter(LearningMemory.memory_type == "VISUAL",
                 LearningMemory.dimension == "editor_style")
         .order_by(LearningMemory.last_validated_at.desc()).limit(limit))
    rows = q.all()
    motions: Counter = Counter()
    shots: Counter = Counter()
    captions: Counter = Counter()
    for r in rows:
        rec = r.recommendation or {}
        motions[str(rec.get("cinematic_motions", ""))] += 1
        shots[str(rec.get("shot_sizes", ""))] += 1
        captions[str(rec.get("caption_style", ""))] += 1
    overused = [m for m, c in motions.items() if c >= max(2, limit - 1) and m and m != "[]"]
    return {
        "overused_motion_patterns": overused,
        "recent_caption_style": captions.most_common(1)[0][0] if captions else None,
        "n": len(rows),
    }
