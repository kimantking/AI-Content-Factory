"""Voice Director V2 (B36, B37): per-phrase performance plan + consistency score.

Deterministic. Reads punctuation, emphasis words, numbers and the scene's story
beat/emotion to set speed / energy / emphasis / pauses / pitch intent per phrase,
staying inside a brand voice band so it varies without becoming a different
narrator every sentence.
"""
from __future__ import annotations

import re
import statistics

from app.video.schema import VoicePerformancePlan, VoicePhrasePlan

_PHRASE_SPLIT = re.compile(r"(?<=[.!?…])\s+|(?<=[,、])\s+|\n+")
_NUM = re.compile(r"\d[\d,.%]*")
_EMPH_CUE = ("절대", "반드시", "핵심", "가장", "단 하나", "지금", "바로", "결국", "정확히")


def _emphasis_words(text: str) -> list[str]:
    out: list[str] = []
    for m in _NUM.finditer(text):
        out.append(m.group(0))
    for w in re.findall(r"[\w가-힣]+", text):
        if w in _EMPH_CUE:
            out.append(w)
    return out[:3]


_BEAT_DELIVERY = {
    "HOOK": ("PUNCHY", 1.06, 0.72),
    "SETUP": ("NARRATION", 1.0, 0.5),
    "QUESTION": ("CURIOUS", 0.98, 0.58),
    "TENSION": ("NARRATION", 1.02, 0.6),
    "DISCOVERY": ("NARRATION", 1.0, 0.6),
    "PROOF": ("MEASURED", 0.94, 0.5),
    "ESCALATION": ("PUNCHY", 1.08, 0.78),
    "CONTRAST": ("MEASURED", 0.96, 0.62),
    "SURPRISE": ("PUNCHY", 1.04, 0.8),
    "PAYOFF": ("WARM", 0.97, 0.6),
    "SUMMARY": ("MEASURED", 0.96, 0.52),
    "CTA": ("WARM", 1.0, 0.58),
    "AFTERTHOUGHT": ("WARM", 0.93, 0.45),
}
_EMOTION_PITCH = {"curiosity": 0.6, "tension": -0.4, "urgency": 0.8, "surprise": 1.0,
                  "relief": -0.6, "confidence": 0.0, "wonder": 0.4, "neutral": 0.0}


def plan_voice(scenes: list[dict], directions: list, *, brand_style: str = "NARRATION",
               formality: float = 0.4, energy_bias: float = 0.55) -> VoicePerformancePlan:
    dmap = {getattr(d, "scene_order", i): d for i, d in enumerate(directions)}
    phrases: list[VoicePhrasePlan] = []
    for i, s in enumerate(scenes):
        so = int(s.get("scene_order", i))
        d = dmap.get(so)
        beat = getattr(d, "story_beat", "SETUP") if d else "SETUP"
        emo = getattr(d, "emotion_intent", "neutral") if d else "neutral"
        style, speed_b, energy_b = _BEAT_DELIVERY.get(beat, ("NARRATION", 1.0, 0.5))
        parts = [p.strip() for p in _PHRASE_SPLIT.split(s.get("narration", "")) if p.strip()]
        for j, ph in enumerate(parts):
            # clamp into a brand band so variation stays subtle
            speed = round(min(1.12, max(0.9, speed_b - formality * 0.04 + (0.02 if _NUM.search(ph) else 0))), 3)
            energy = round(min(0.9, max(0.3, energy_b * (0.6 + 0.4 * energy_bias))), 3)
            emph = _emphasis_words(ph)
            pause_after = 0.32 if ph.endswith((".", "!", "?", "…")) else 0.16
            pause_before = 0.28 if (j == 0 and beat in ("SURPRISE", "PAYOFF", "CONTRAST")) else 0.0
            phrases.append(VoicePhrasePlan(
                scene_order=so, text=ph, speed=speed, energy=energy,
                emotion=emo, emphasis=emph, pause_before=pause_before,
                pause_after=pause_after,
                pitch=round(_EMOTION_PITCH.get(emo, 0.0) * (0.5 if formality > 0.6 else 1.0), 2),
                volume_intent=1.0 if beat not in ("AFTERTHOUGHT",) else 0.92,
                delivery_style=style,
            ))
    score, notes = consistency_score(phrases)
    plan = VoicePerformancePlan(phrases=phrases, consistency_score=score,
                                brand_style=brand_style, notes=notes)
    return annotate_pauses(plan)


def classify_pause(pause_s: float, *, at_sentence_end: bool, before_emphasis: bool,
                   at_beat_change: bool) -> str:
    """BREATH | EMPHASIS | DRAMATIC | UNNECESSARY (B29). Not every silence is
    removed — breath and dramatic pauses are kept."""
    if pause_s <= 0.05:
        return "NONE"
    if before_emphasis or at_beat_change:
        return "DRAMATIC" if pause_s >= 0.4 else "EMPHASIS"
    if at_sentence_end:
        return "BREATH"
    if pause_s >= 0.35:
        return "DRAMATIC"
    return "UNNECESSARY" if pause_s < 0.12 else "BREATH"


def annotate_pauses(plan: VoicePerformancePlan) -> VoicePerformancePlan:
    prev_scene = None
    for p in plan.phrases:
        beat_change = p.scene_order != prev_scene
        at_end = p.text.rstrip().endswith((".", "!", "?", "…"))
        kind = classify_pause(p.pause_after, at_sentence_end=at_end,
                              before_emphasis=bool(p.emphasis), at_beat_change=beat_change)
        p.pause_after_kind = kind
        prev_scene = p.scene_order
    return plan


def consistency_score(phrases: list[VoicePhrasePlan]) -> tuple[float, list[str]]:
    """Natural variation is good; a different narrator every sentence is not (B37)."""
    if len(phrases) < 3:
        return 1.0, []
    speeds = [p.speed for p in phrases]
    energies = [p.energy for p in phrases]
    notes: list[str] = []
    s_sd = statistics.pstdev(speeds)
    e_sd = statistics.pstdev(energies)
    # target: some movement (>0.01) but bounded (<0.09 speed, <0.18 energy)
    score = 1.0
    if s_sd > 0.09:
        score -= min(0.4, (s_sd - 0.09) * 4)
        notes.append(f"speed varies too much across phrases (sd={s_sd:.3f})")
    if e_sd > 0.20:
        score -= min(0.3, (e_sd - 0.20) * 3)
        notes.append(f"energy varies too much across phrases (sd={e_sd:.3f})")
    # jump between adjacent phrases
    jumps = sum(1 for a, b in zip(speeds, speeds[1:]) if abs(a - b) > 0.1)
    if jumps:
        score -= min(0.3, jumps * 0.06)
        notes.append(f"{jumps} abrupt speed jump(s) between adjacent phrases")
    return round(max(0.0, score), 3), notes
