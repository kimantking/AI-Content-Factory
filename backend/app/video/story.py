"""Story Director + Emotional Arc (B2, B3).

Turns a flat scene list into a designed emotional journey. Deterministic: it maps
narration cues (position, questions, numbers, contrast words, CTA phrases) onto a
beat vocabulary and an emotion curve. It never forces every beat into every video.
"""
from __future__ import annotations

import re

from app.video.schema import StoryBeat

_Q = ("?", "왜", "어떻게", "무엇", "정말", "진짜")
_CONTRAST = ("하지만", "반대로", "그러나", "오히려", "그런데도", "의외로", "착각", "오해")
_PROOF = ("데이터", "통계", "수치", "연구", "조사", "출처", "실제로", "%", "배", "조사에 따르면")
_ESCALATE = ("게다가", "심지어", "더 큰 문제", "그뿐만", "여기서 끝이", "더 나아가")
_SURPRISE = ("놀랍게도", "충격", "예상과 달리", "믿기 어렵", "반전")
_CTA = ("구독", "팔로우", "저장", "댓글", "공유", "다음 편", "링크")
_NUM = re.compile(r"\d[\d,.%]*")


def _cue(text: str, words: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(w in low for w in words)


def assign_beats(narrations: list[str]) -> list[str]:
    """One beat label per scene. Position-aware with cue overrides."""
    n = len(narrations)
    if n == 0:
        return []
    beats: list[str] = []
    for i, raw in enumerate(narrations):
        t = raw or ""
        pos = i / max(1, n - 1)
        beat = "SETUP"
        if i == 0:
            beat = "HOOK"
        elif i == n - 1:
            beat = "CTA" if _cue(t, _CTA) else "PAYOFF"
        elif i == n - 2 and _cue(t, _CTA):
            beat = "CTA"
        elif _cue(t, _SURPRISE):
            beat = "SURPRISE"
        elif _cue(t, _CONTRAST):
            beat = "CONTRAST"
        elif _cue(t, _ESCALATE):
            beat = "ESCALATION"
        elif _cue(t, _PROOF) or _NUM.search(t):
            beat = "PROOF"
        elif _cue(t, _Q):
            beat = "QUESTION"
        elif pos < 0.28:
            beat = "SETUP"
        elif pos < 0.5:
            beat = "TENSION"
        elif pos < 0.72:
            beat = "DISCOVERY"
        else:
            beat = "SUMMARY"
        beats.append(beat)
    # a video that never resolves feels broken — guarantee a PAYOFF before CTA
    if "PAYOFF" not in beats and beats[-1] == "CTA" and n >= 3:
        beats[-2] = "PAYOFF"
    return beats


_EMOTION_FOR_BEAT = {
    "HOOK": "curiosity", "SETUP": "curiosity", "QUESTION": "curiosity",
    "TENSION": "tension", "ESCALATION": "urgency", "CONTRAST": "surprise",
    "DISCOVERY": "wonder", "PROOF": "confidence", "SURPRISE": "surprise",
    "PAYOFF": "relief", "SUMMARY": "confidence", "CTA": "confidence",
    "AFTERTHOUGHT": "wonder",
}


def emotion_arc(beats: list[str]) -> list[str]:
    """Emotion intent per scene, smoothed so it moves, not oscillates wildly."""
    raw = [_EMOTION_FOR_BEAT.get(b, "neutral") for b in beats]
    out: list[str] = []
    for i, e in enumerate(raw):
        # don't allow relief before any tension/urgency has happened
        if e == "relief" and not any(x in ("tension", "urgency", "surprise") for x in out):
            e = "confidence"
        out.append(e)
    return out


def build_story_arc(narrations: list[str]) -> tuple[list[str], list[str], list[StoryBeat]]:
    beats = assign_beats(narrations)
    emos = emotion_arc(beats)
    # group consecutive identical beats into StoryBeat segments
    arc: list[StoryBeat] = []
    i = 0
    while i < len(beats):
        j = i
        while j + 1 < len(beats) and beats[j + 1] == beats[i]:
            j += 1
        arc.append(StoryBeat(
            beat=beats[i], scene_orders=list(range(i, j + 1)),
            emotion_from=emos[i], emotion_to=emos[j],
            purpose=_PURPOSE.get(beats[i], "advance the story"),
        ))
        i = j + 1
    return beats, emos, arc


_PURPOSE = {
    "HOOK": "stop the scroll, promise value",
    "SETUP": "orient the viewer",
    "QUESTION": "open a curiosity loop",
    "TENSION": "raise the stakes",
    "DISCOVERY": "reveal the core idea",
    "PROOF": "back the claim with evidence",
    "ESCALATION": "add a bigger consequence",
    "CONTRAST": "subvert the expectation",
    "SURPRISE": "deliver an unexpected turn",
    "PAYOFF": "resolve the loop, give the takeaway",
    "SUMMARY": "consolidate what matters",
    "CTA": "ask for one specific action",
    "AFTERTHOUGHT": "leave a lingering thought",
}
