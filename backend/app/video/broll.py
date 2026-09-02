"""B-roll Director (B15-B19): extended scoring, kind classification, story-sequence
evaluation, visual-evidence priority.

Deterministic. Scores candidate stock/visual items against a scene on 9 axes and
classifies the *kind* of B-roll (direct / contextual / metaphorical / ...). It
never rewards "pretty but meaningless" footage — narrative + context relevance
dominate the weight.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.analytics.embedding import cosine, embed

_NUM = re.compile(r"\d[\d,.%]*")
_EVIDENCE_CUE = ("데이터", "통계", "수치", "연구", "조사", "보고서", "발표", "출처", "%", "그래프", "차트")
_PROCESS_CUE = ("과정", "단계", "방법", "절차", "어떻게", "흐름")
_ATMOSPHERE_CUE = ("분위기", "느낌", "긴장", "불안", "희망", "미래")
_METAPHOR_MAP = {
    "경쟁": ["질주하는 사람", "달리기", "체스", "레이스"],
    "속도": ["고속도로", "빠르게 지나가는 풍경", "타임랩스"],
    "성장": ["새싹", "차트 상승", "계단 오르기"],
    "붕괴": ["무너지는 구조물", "도미노", "균열"],
    "연결": ["네트워크 노드", "도시 야경", "다리"],
    "자동화": ["로봇 팔", "컨베이어 벨트", "서버실"],
    "변화": ["계절 전환", "탈피", "리모델링"],
}

_WEIGHTS = {
    "semantic": 0.20, "narrative": 0.22, "emotional": 0.12, "visual_quality": 0.10,
    "motion_quality": 0.08, "shot_compat": 0.08, "novelty": 0.08,
    "license": 0.06, "context_accuracy": 0.06,
}


@dataclass
class BrollCandidate:
    ref: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    has_motion: bool = True
    width: int = 1920
    height: int = 1080
    quality_hint: float = 0.7        # 0..1 provider-reported
    license_ok: bool = True
    provider_mode: str = "MOCK"


@dataclass
class BrollScore:
    ref: str
    total: float
    kind: str
    axes: dict[str, float]
    reasons: list[str] = field(default_factory=list)


def classify_kind(scene_narration: str, cand: BrollCandidate) -> str:
    t = (scene_narration or "").lower()
    desc = (cand.description or "").lower()
    if any(c in t for c in _EVIDENCE_CUE) and any(k in desc for k in ("chart", "graph", "screen", "document", "차트", "그래프", "화면")):
        return "PROOF"
    if any(c in t for c in _PROCESS_CUE):
        return "PROCESS"
    # direct: candidate words overlap the scene's concrete nouns
    scene_toks = set(re.findall(r"[\w가-힣]{2,}", t))
    desc_toks = set(re.findall(r"[\w가-힣]{2,}", desc))
    if len(scene_toks & desc_toks) >= 2:
        return "DIRECT"
    for concept, metas in _METAPHOR_MAP.items():
        if concept in t and any(m.split()[0] in desc for m in metas):
            return "METAPHORICAL"
    if any(c in t for c in _ATMOSPHERE_CUE):
        return "ATMOSPHERIC"
    if _NUM.search(scene_narration or "") or any(w in t for w in ("정확히", "구체적")):
        return "DETAIL"
    return "CONTEXTUAL"


def score_candidate(scene: dict, cand: BrollCandidate, *, recent_refs: list[str] | None = None,
                    beat: str = "SETUP", emotion: str = "neutral") -> BrollScore:
    narr = scene.get("narration", "") or scene.get("visual_description", "")
    v_scene = embed(narr)
    v_cand = embed(cand.description + " " + " ".join(cand.tags))
    axes: dict[str, float] = {}
    reasons: list[str] = []

    axes["semantic"] = max(0.0, cosine(v_scene, v_cand))
    # narrative relevance: does it serve the beat's job?
    kind = classify_kind(narr, cand)
    beat_fit = {
        "HOOK": {"DIRECT": 0.7, "METAPHORICAL": 0.9, "ATMOSPHERIC": 0.8},
        "PROOF": {"PROOF": 1.0, "DETAIL": 0.8, "DIRECT": 0.6},
        "SETUP": {"CONTEXTUAL": 0.9, "DIRECT": 0.7, "ATMOSPHERIC": 0.6},
        "CONTRAST": {"METAPHORICAL": 0.9, "DIRECT": 0.6},
        "PAYOFF": {"DIRECT": 0.8, "CONTEXTUAL": 0.7},
    }.get(beat, {})
    axes["narrative"] = beat_fit.get(kind, 0.5)
    axes["emotional"] = 0.7 if (emotion in ("tension", "urgency") and cand.has_motion) or \
                              (emotion in ("confidence", "relief") and not cand.has_motion) else 0.5
    axes["visual_quality"] = cand.quality_hint
    axes["motion_quality"] = 0.75 if cand.has_motion else 0.45
    # shot compat: aspect close to a vertical/landscape need is handled elsewhere; here reward >= HD
    axes["shot_compat"] = 0.8 if (cand.width >= 1280 and cand.height >= 720) else 0.4
    recent = set(recent_refs or [])
    axes["novelty"] = 0.3 if cand.ref in recent else 1.0
    axes["license"] = 1.0 if cand.license_ok else 0.0
    axes["context_accuracy"] = 0.85 if kind in ("DIRECT", "PROOF", "DETAIL") else 0.6

    if not cand.license_ok:
        reasons.append("license not cleared → disqualified")
        total = 0.0
    else:
        total = sum(_WEIGHTS[k] * axes[k] for k in _WEIGHTS)
    if axes["semantic"] < 0.2 and axes["narrative"] < 0.55:
        reasons.append("weak semantic + narrative link — risks 'pretty but meaningless'")
        total *= 0.6
    return BrollScore(ref=cand.ref, total=round(total, 4), kind=kind,
                      axes={k: round(v, 3) for k, v in axes.items()}, reasons=reasons)


def rank(scene: dict, candidates: list[BrollCandidate], **kw) -> list[BrollScore]:
    scored = [score_candidate(scene, c, **kw) for c in candidates]
    scored.sort(key=lambda s: s.total, reverse=True)
    return scored


def visual_evidence_priority(scene: dict) -> bool:
    """True if this scene makes a claim that a screenshot/chart/real doc would prove
    better than a generic AI image (B18)."""
    narr = scene.get("narration", "") or ""
    if _NUM.search(narr):
        return True
    return any(c in narr for c in _EVIDENCE_CUE)


def story_sequence_score(kinds: list[str]) -> tuple[float, list[str]]:
    """Do consecutive B-roll kinds build a mini-progression rather than random cuts (B17)?"""
    notes: list[str] = []
    if len(kinds) < 3:
        return 1.0, notes
    # reward: a scene-setting kind early, proof/detail later, not all-atmospheric
    atmos = sum(1 for k in kinds if k == "ATMOSPHERIC")
    proof = sum(1 for k in kinds if k in ("PROOF", "DETAIL", "DIRECT"))
    score = 0.5
    if kinds[0] in ("CONTEXTUAL", "ATMOSPHERIC", "DIRECT"):
        score += 0.2
    if proof >= max(1, len(kinds) // 3):
        score += 0.2
    if atmos > len(kinds) * 0.5:
        score -= 0.3
        notes.append("more than half the B-roll is atmospheric — thin on information")
    # penalise long runs of the identical kind
    for i in range(2, len(kinds)):
        if kinds[i] == kinds[i - 1] == kinds[i - 2]:
            score -= 0.15
            notes.append(f"B-roll kind '{kinds[i]}' repeats 3x at {i-2}-{i}")
            break
    return max(0.0, min(1.0, score + 0.1)), notes
