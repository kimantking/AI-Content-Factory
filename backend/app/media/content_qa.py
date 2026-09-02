from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = re.compile(r"\d[\d,.%]*")


@dataclass
class ContentQAReport:
    scores: dict[str, float]
    overall: float
    weak_scenes: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.overall >= 0.6 and not self.weak_scenes


def evaluate(*, scenes: list[dict], subtitle_coverage: float, ai_video_ratio: float,
             stock_ratio: float, distinct_motions: int, usable_fact_texts: list[str],
             media_qa_passed: bool) -> ContentQAReport:
    notes: list[str] = []
    weak: list[int] = []

    # visual diversity: penalise if every scene is the same visual_type or motion
    vtypes = {s.get("visual_type") for s in scenes}
    visual_quality = 0.5 + 0.1 * min(3, len(vtypes)) + (0.1 if distinct_motions >= 3 else 0.0)
    visual_quality = min(1.0, visual_quality)

    subtitle_quality = min(1.0, 0.4 + subtitle_coverage * 0.6)
    audio_quality = 0.8 if media_qa_passed else 0.4

    # content consistency: every scene narration should relate to a usable fact or the topic
    fact_blob = " ".join(usable_fact_texts).lower()
    related = 0
    for i, s in enumerate(scenes):
        narr = (s.get("narration") or "").lower()
        nums = set(_NUM.findall(narr))
        fact_nums = set(_NUM.findall(fact_blob))
        if not nums or nums <= fact_nums:
            related += 1
        else:
            weak.append(i + 1)
            notes.append(f"scene {i + 1}: number not traceable to verified facts")
    consistency = related / max(1, len(scenes))

    originality = 1.0 - min(0.5, ai_video_ratio * 0.5)  # heavy AI video reads as slop
    platform_fit = 0.8

    scores = {
        "visual_quality": round(visual_quality, 2),
        "subtitle_quality": round(subtitle_quality, 2),
        "audio_quality": round(audio_quality, 2),
        "content_consistency": round(consistency, 2),
        "originality": round(originality, 2),
        "platform_fit": platform_fit,
    }
    overall = round(sum(scores.values()) / len(scores), 3)
    return ContentQAReport(scores=scores, overall=overall, weak_scenes=weak, notes=notes)
