"""Retention Director + Boredom Detector (B4, B5, B6, B82).

Deterministic analysis of a planned scene list for watch-through risk. No fake
retention numbers — if there is no Phase-3 retention data, this reports *design*
signals ("why would someone keep watching here?"), not a predicted curve.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = re.compile(r"\d[\d,.%]*")
_OPEN_LOOP = ("나중에", "곧", "먼저", "일단", "이유는", "뒤에서", "마지막에", "결론부터", "핵심은")
_PAYOFF_CUE = ("결론", "정리하면", "핵심은", "요약하면", "그래서", "결과적으로")


@dataclass
class RetentionCheckpoint:
    label: str
    t: float
    scene_order: int
    reason_to_stay: str
    risk: str          # LOW | MEDIUM | HIGH


@dataclass
class RetentionReport:
    checkpoints: list[RetentionCheckpoint] = field(default_factory=list)
    first_second_strength: float = 0.0     # 0..1
    early_payoff: bool = False
    open_loops: int = 0
    pattern_interrupts: list[int] = field(default_factory=list)   # scene_orders
    boredom_risk: float = 0.0
    boredom_spans: list[tuple[int, int]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


_SHORT_LABELS = [("0s", 0.0), ("1s", 1.0), ("3s", 3.0), ("5s", 5.0), ("10s", 10.0),
                 ("25%", None), ("50%", None), ("75%", None), ("CTA", None)]


def _scene_at(scenes: list[dict], t: float) -> int:
    acc = 0.0
    for s in scenes:
        acc += float(s.get("estimated_duration", s.get("duration", 4.0)))
        if t <= acc:
            return int(s.get("scene_order", 0))
    return int(scenes[-1].get("scene_order", 0)) if scenes else 0


def first_second_strength(hook_narration: str, hook_beat: str) -> float:
    t = (hook_narration or "").strip()
    score = 0.25
    if hook_beat == "HOOK":
        score += 0.2
    if _NUM.search(t):
        score += 0.2
    if t.endswith("?") or any(q in t for q in ("왜", "어떻게")):
        score += 0.15
    if 3 <= len(t.split()) <= 14:
        score += 0.2
    banned = ("안녕하세요", "오늘은", "이번 영상", "구독")
    if any(b in t for b in banned):
        score -= 0.4
    return max(0.0, min(1.0, score))


def _dimension_key(s: dict, direction) -> tuple:
    return (
        s.get("visual_type"),
        getattr(direction, "shot_size", None) if direction else None,
        getattr(direction, "motion_energy", None) if direction else None,
        s.get("camera_motion"),
        getattr(direction, "primary_focus", None) if direction else None,
    )


def boredom_scan(scenes: list[dict], directions: list) -> tuple[float, list[tuple[int, int]], list[int]]:
    """Flag runs where too many visual/audio/information dimensions stay constant.
    Returns (risk 0..1, boring spans as (start_order,end_order), pattern-interrupt scene_orders)."""
    dmap = {getattr(d, "scene_order", i): d for i, d in enumerate(directions)}
    keys = [_dimension_key(s, dmap.get(int(s.get("scene_order", i)))) for i, s in enumerate(scenes)]
    spans: list[tuple[int, int]] = []
    interrupts: list[int] = []
    run_start = 0
    worst_run = 1
    for i in range(1, len(keys)):
        same = sum(1 for a, b in zip(keys[i], keys[i - 1]) if a == b and a is not None)
        if same >= 4:  # 4+ of 5 dimensions unchanged
            continue
        run_len = i - run_start
        worst_run = max(worst_run, run_len)
        if run_len >= 3:
            spans.append((int(scenes[run_start].get("scene_order", run_start)),
                          int(scenes[i - 1].get("scene_order", i - 1))))
        interrupts.append(int(scenes[i].get("scene_order", i)))
        run_start = i
    tail = len(keys) - run_start
    if tail >= 3:
        spans.append((int(scenes[run_start].get("scene_order", run_start)),
                      int(scenes[-1].get("scene_order", len(scenes) - 1))))
    worst_run = max(worst_run, tail)
    risk = max(0.0, min(1.0, (worst_run - 2) / 5.0 + 0.12 * len(spans)))
    return round(risk, 3), spans, interrupts


def analyze(scenes: list[dict], directions: list, *, is_short: bool = True) -> RetentionReport:
    if not scenes:
        return RetentionReport()
    total = sum(float(s.get("estimated_duration", s.get("duration", 4.0))) for s in scenes)
    dmap = {getattr(d, "scene_order", i): d for i, d in enumerate(directions)}

    first = scenes[0]
    first_dir = dmap.get(int(first.get("scene_order", 0)))
    fss = first_second_strength(first.get("narration", ""),
                                getattr(first_dir, "story_beat", "HOOK") if first_dir else "HOOK")

    # payoff position
    payoff_t = None
    acc = 0.0
    for s in scenes:
        acc += float(s.get("estimated_duration", s.get("duration", 4.0)))
        d = dmap.get(int(s.get("scene_order", 0)))
        if (d and getattr(d, "story_beat", "") in ("DISCOVERY", "PROOF", "PAYOFF")) or \
           any(c in (s.get("narration") or "") for c in _PAYOFF_CUE):
            payoff_t = acc
            break
    early_payoff = payoff_t is not None and payoff_t <= (0.45 * total if is_short else 0.6 * total)

    open_loops = sum(1 for s in scenes if any(c in (s.get("narration") or "") for c in _OPEN_LOOP))

    boredom, spans, interrupts = boredom_scan(scenes, directions)

    cps: list[RetentionCheckpoint] = []
    marks = ([("0s", 0.0), ("1s", 1.0), ("3s", 3.0), ("5s", 5.0), ("10s", 10.0),
              ("50%", total * 0.5), ("75%", total * 0.75), ("CTA", max(0.0, total - 3.0))]
             if is_short else
             [("intro", 0.0), ("30s", 30.0), ("1m", 60.0), ("50%", total * 0.5),
              ("75%", total * 0.75), ("CTA", max(0.0, total - 8.0))])
    for label, t in marks:
        if t > total:
            continue
        so = _scene_at(scenes, t)
        d = dmap.get(so)
        beat = getattr(d, "story_beat", "SETUP") if d else "SETUP"
        reason, risk = _reason_and_risk(label, beat, t, total, fss, early_payoff,
                                        so in [x for span in spans for x in range(span[0], span[1] + 1)])
        cps.append(RetentionCheckpoint(label=label, t=round(t, 2), scene_order=so,
                                       reason_to_stay=reason, risk=risk))

    notes: list[str] = []
    if fss < 0.45:
        notes.append("weak first second — hook lacks a number/question/tight length")
    if not early_payoff:
        notes.append("no early payoff — first concrete reveal lands late")
    if open_loops == 0 and len(scenes) > 4:
        notes.append("no open loop set up — nothing pulls the viewer forward")
    if boredom >= 0.5:
        notes.append(f"boredom risk {boredom:.0%}: {len(spans)} low-variation span(s)")

    return RetentionReport(
        checkpoints=cps, first_second_strength=round(fss, 3), early_payoff=early_payoff,
        open_loops=open_loops, pattern_interrupts=interrupts, boredom_risk=boredom,
        boredom_spans=spans, notes=notes,
    )


def _reason_and_risk(label, beat, t, total, fss, early_payoff, in_boring_span):
    if label in ("0s", "1s", "intro"):
        return ("hook promise", "LOW" if fss >= 0.5 else "HIGH")
    if label in ("3s", "5s"):
        return ("curiosity loop still open", "LOW" if not in_boring_span else "MEDIUM")
    if label in ("10s", "30s"):
        return ("first concrete payoff", "LOW" if early_payoff else "HIGH")
    if label == "50%":
        return ("mid-point escalation / new angle", "MEDIUM" if in_boring_span else "LOW")
    if label == "75%":
        return ("build toward resolution", "MEDIUM" if in_boring_span else "LOW")
    if label == "CTA":
        return ("payoff delivered, one clear ask", "LOW")
    return ("progression", "MEDIUM" if in_boring_span else "LOW")
