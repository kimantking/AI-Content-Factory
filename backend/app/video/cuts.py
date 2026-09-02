"""Cut Engine V2 (B12) — score candidate cut points instead of cutting on fixed
seconds. Deterministic. Signals: speech boundary, phrase boundary, story beat
change, visual change, motion peak, scene boundary, audio onset, emphasis,
reaction, information change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = re.compile(r"\d[\d,.%]*")
_EMPHASIS = ("!", "핵심", "바로", "결국", "단 하나", "지금", "절대", "명심")
_REACTION = ("놀랍", "충격", "믿기", "반전", "예상과 달리", "설마")
_SENT_END = re.compile(r"[.!?…]\s*$")
_PHRASE_END = re.compile(r"[,、·]\s*$|[은는이가을를에서]\s*$")


@dataclass
class CutPoint:
    t: float
    scene_order: int
    score: float
    reasons: list[str] = field(default_factory=list)
    kind: str = "SOFT"          # HARD | SOFT


def _dur(s: dict) -> float:
    return float(s.get("estimated_duration", s.get("duration", 4.0))) or 4.0


def score_cuts(scenes: list[dict], directions: list, *,
               audio_onsets: list[float] | None = None,
               min_gap: float = 0.9) -> list[CutPoint]:
    """Return scored cut points along the timeline. Scene boundaries are HARD
    cuts; mid-scene candidates (phrase / emphasis / reaction) are SOFT."""
    dmap = {getattr(d, "scene_order", i): d for i, d in enumerate(directions)}
    onsets = sorted(audio_onsets or [])
    pts: list[CutPoint] = []
    t = 0.0
    prev_beat = None
    prev_vtype = None
    for i, s in enumerate(scenes):
        so = int(s.get("scene_order", i))
        d = dmap.get(so)
        beat = getattr(d, "story_beat", "SETUP") if d else "SETUP"
        vtype = s.get("visual_type")
        narr = s.get("narration", "") or ""

        # scene boundary = HARD cut
        reasons = ["scene_boundary"]
        score = 0.6
        if beat != prev_beat and prev_beat is not None:
            reasons.append(f"story_beat_change:{prev_beat}->{beat}")
            score += 0.2
        if vtype != prev_vtype and prev_vtype is not None:
            reasons.append("visual_change")
            score += 0.15
        if _NUM.search(narr):
            reasons.append("information_change:number")
            score += 0.1
        near_onset = any(abs(o - t) < 0.25 for o in onsets)
        if near_onset:
            reasons.append("audio_onset")
            score += 0.1
        pts.append(CutPoint(t=round(t, 3), scene_order=so, score=round(min(1.0, score), 3),
                            reasons=reasons, kind="HARD"))

        # one SOFT mid-scene candidate at the strongest internal moment
        dur = _dur(s)
        if dur >= 3.0:
            mid_t = t + dur * 0.55
            sreasons: list[str] = []
            sscore = 0.2
            if any(k in narr for k in _EMPHASIS):
                sreasons.append("emphasis")
                sscore += 0.25
            if any(k in narr for k in _REACTION):
                sreasons.append("reaction")
                sscore += 0.25
            # phrase boundary near the midpoint
            words = narr.split()
            if len(words) >= 6:
                sreasons.append("phrase_boundary")
                sscore += 0.15
            onset_here = min((abs(o - mid_t) for o in onsets), default=9.9)
            if onset_here < 0.2:
                sreasons.append("audio_onset")
                sscore += 0.15
            if sreasons:
                pts.append(CutPoint(t=round(mid_t, 3), scene_order=so,
                                    score=round(min(1.0, sscore), 3),
                                    reasons=sreasons, kind="SOFT"))
        prev_beat, prev_vtype = beat, vtype
        t += dur

    # enforce a minimum gap between accepted cuts (drop the weaker of a close pair)
    pts.sort(key=lambda p: p.t)
    kept: list[CutPoint] = []
    for p in pts:
        if kept and (p.t - kept[-1].t) < min_gap:
            if p.score > kept[-1].score and kept[-1].kind != "HARD":
                kept[-1] = p
            continue
        kept.append(p)
    return kept


def cut_rhythm_report(cuts: list[CutPoint]) -> dict:
    if len(cuts) < 2:
        return {"n": len(cuts), "avg_gap": 0.0, "flag": "OK"}
    gaps = [b.t - a.t for a, b in zip(cuts, cuts[1:])]
    import statistics
    avg = statistics.fmean(gaps)
    sd = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
    # a good edit varies; near-zero variance = mechanical fixed-interval cutting
    flag = "MECHANICAL" if avg > 0 and sd / avg < 0.12 else "OK"
    return {"n": len(cuts), "avg_gap": round(avg, 2), "gap_cv": round(sd / avg, 3) if avg else 0.0,
            "flag": flag, "hard": sum(1 for c in cuts if c.kind == "HARD")}
