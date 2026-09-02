from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

# AI writing "tells" (Design Amendment §4). This is a CONTENT-QUALITY signal,
# not an "AI detector evasion" score.

_BANNED_OPENERS = [
    "안녕하세요 여러분",
    "오늘은",
    "지금부터 자세히 살펴보겠습니다",
    "이번 시간에는",
    "본격적으로",
]
_CLICHE_PHRASES = [
    "여러분은 어떻게 생각하시나요",
    "어떻게 생각하시나요",
    "결론적으로",
    "다시 한 번 말씀드리면",
    "정리하자면",
    "in conclusion",
    "let's dive in",
    "what do you think",
]
_OVERUSED_CONNECTIVES = [
    "그리고", "하지만", "또한", "따라서", "그러나", "게다가",
    "however", "moreover", "additionally", "furthermore",
]
_FILLER_INTENSIFIERS = ["매우", "정말", "굉장히", "너무나", "아주", "very", "really", "extremely"]
_IMPORTANCE_MARKERS = ["중요합니다", "중요한 점은", "핵심은", "기억하세요", "important", "key takeaway"]

_SENT_SPLIT = re.compile(r"(?<=[.!?。…])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def _word_lens(sentences: list[str]) -> list[int]:
    return [len(s.split()) for s in sentences] or [0]


@dataclass
class AISlopReport:
    score: float                      # 0..100, higher = more machine-like
    burstiness: float                 # stdev of sentence word-counts
    breakdown: dict[str, float] = field(default_factory=dict)
    tells: list[str] = field(default_factory=list)

    @property
    def passes(self) -> bool:  # convenience; real threshold check is caller's job
        return self.score <= 20


def score_ai_slop(text: str, *, max_target: int = 20) -> AISlopReport:
    sentences = _sentences(text)
    n = max(1, len(sentences))
    lens = _word_lens(sentences)
    mean_len = statistics.fmean(lens)
    burstiness = statistics.pstdev(lens) if len(lens) > 1 else 0.0

    breakdown: dict[str, float] = {}
    tells: list[str] = []
    low = text.lower()

    # 1. Uniform sentence length -> low burstiness relative to mean.
    uniformity = 0.0
    if mean_len > 0:
        cv = burstiness / mean_len  # coefficient of variation
        if cv < 0.45:
            uniformity = min(25.0, (0.45 - cv) / 0.45 * 25.0)
            if uniformity > 6:
                tells.append("문장 길이가 지나치게 균일함 (낮은 burstiness)")
    breakdown["uniform_sentence_length"] = round(uniformity, 1)

    # 2. Repeated connectives.
    conn_hits = sum(low.count(c) for c in _OVERUSED_CONNECTIVES)
    conn_score = min(15.0, max(0.0, (conn_hits / n - 0.25)) * 60.0)
    if conn_score > 4:
        tells.append("같은 접속어 반복")
    breakdown["repeated_connectives"] = round(conn_score, 1)

    # 3. Importance markers ("중요합니다" 남발).
    imp_hits = sum(low.count(m.lower()) for m in _IMPORTANCE_MARKERS)
    imp_score = min(12.0, imp_hits * 4.0)
    if imp_score > 4:
        tells.append("'중요합니다' 류 표현 남발")
    breakdown["importance_markers"] = round(imp_score, 1)

    # 4. Cliche phrases / canned CTA.
    cliche_hits = sum(1 for p in _CLICHE_PHRASES if p in low)
    cliche_score = min(15.0, cliche_hits * 7.5)
    if cliche_hits:
        tells.append("뻔한 관용구 / CTA")
    breakdown["cliches"] = round(cliche_score, 1)

    # 5. Banned template openers.
    first_two = " ".join(sentences[:2]).lower() if sentences else ""
    opener_score = 0.0
    for op in _BANNED_OPENERS:
        if first_two.startswith(op) or first_two.startswith(op.replace(" ", "")):
            opener_score = 12.0
            tells.append("템플릿형 도입부")
            break
    breakdown["template_opener"] = opener_score

    # 6. Excessive rigid 3-part structure (lots of 3-item bullet groups).
    bullet_groups = re.findall(r"(?:^[-*•].*\n){3,}", text + "\n", flags=re.MULTILINE)
    triad_score = min(10.0, len(bullet_groups) * 5.0)
    if triad_score > 4:
        tells.append("과도하게 정돈된 3단 목록 구조")
    breakdown["rigid_triads"] = round(triad_score, 1)

    # 7. Filler intensifiers.
    filler_hits = sum(low.count(f) for f in _FILLER_INTENSIFIERS)
    filler_score = min(8.0, max(0.0, filler_hits / n - 0.2) * 30.0)
    if filler_score > 3:
        tells.append("의미 없는 수식어 반복")
    breakdown["filler_intensifiers"] = round(filler_score, 1)

    # 8. Identical paragraph opening pattern.
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    para_score = 0.0
    if len(paras) >= 3:
        first_tokens = [p.split()[0] if p.split() else "" for p in paras]
        if len(set(first_tokens)) <= max(1, len(first_tokens) // 3):
            para_score = 8.0
            tells.append("모든 문단이 같은 방식으로 시작")
    breakdown["uniform_paragraph_start"] = para_score

    score = min(100.0, sum(breakdown.values()))
    return AISlopReport(
        score=round(score, 1),
        burstiness=round(burstiness, 2),
        breakdown=breakdown,
        tells=tells,
    )
