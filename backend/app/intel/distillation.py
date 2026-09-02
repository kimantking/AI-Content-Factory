"""Prompt Distillation Engine.

We do NOT claim to recover the original creator's prompt. We reverse-infer: "what
production instructions would OUR agent need to reproduce the good, verifiable
features of this result?" — a `PromptBlueprint`.

Guards:
  * Single-source guard — one reference can only reach OBSERVED / EXPERIMENTAL
    (`learning_single_source_max_status`), never PROMOTED.
  * Multi-reference confidence — sample_size + source diversity + consistency.
  * AUTO_PROMOTE_LEARNED_PROMPTS is false — production adoption needs a human or a
    VALIDATED experiment.
  * Every blueprint keeps traceable `PromptBlueprintEvidence`.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models_learn import (
    BLUEPRINT_STATUS,
    PromptBlueprint,
    PromptBlueprintEvidence,
)

# state machine (spec §W / §BY)
_TRANSITIONS = {
    "OBSERVED": {"EXPERIMENTAL", "REJECTED", "DEPRECATED"},
    "EXPERIMENTAL": {"CANDIDATE", "REJECTED", "DEPRECATED", "OBSERVED"},
    "CANDIDATE": {"VALIDATED", "EXPERIMENTAL", "REJECTED", "DEPRECATED"},
    "VALIDATED": {"PROMOTED", "CANDIDATE", "DEPRECATED", "REJECTED"},
    "PROMOTED": {"DEPRECATED", "VALIDATED"},          # rollback -> VALIDATED
    "DEPRECATED": {"EXPERIMENTAL", "REJECTED"},
    "REJECTED": set(),
}
_ORDER = {s: i for i, s in enumerate(
    ["OBSERVED", "EXPERIMENTAL", "CANDIDATE", "VALIDATED", "PROMOTED"])}


def valid_transition(frm: str, to: str) -> bool:
    return to in _TRANSITIONS.get(frm, set())


# analysis kind -> (agent_type, [(feature_key, instruction, is_constraint)])
def _blueprint_lines(agent_type: str, kind: str, merged: dict) -> dict:
    """Turn a merged (multi-reference) feature summary into production guidance.
    Deterministic; conservative; no verbatim copy of source text."""
    ins: list[str] = []
    con: list[str] = []
    pos: list[str] = []
    neg: list[str] = []

    if kind == "HOOK_PATTERN":
        tags = merged.get("common_hook_tags", [])
        if "FAST_HOOK" in tags:
            ins.append("첫 3초 안에 핵심 시청 이유(promise)를 제시한다.")
        if "QUESTION" in tags:
            pos.append("호기심을 유발하는 질문형 오프닝")
        con.append("검증되지 않은 과장·확정 표현은 사용하지 않는다.")
        neg.append("clickbait 과장(‘충격’, ‘무조건’)")
    elif kind == "EDITING_PROFILE":
        rr = merged.get("scene_duration_mean")
        if isinstance(rr, (int, float)) and rr <= 3.5:
            ins.append("장면 평균 길이를 짧게(≈3초) 유지해 시각적 리듬을 만든다.")
        ins.append("정보가 바뀌는 지점마다 컷/비주얼을 전환한다.")
    elif kind == "BROLL_PROFILE":
        ins.append("통계·수치 Claim에는 generic B-roll 대신 데이터 시각화를 우선한다.")
        con.append("내레이션 의미와 무관한 스톡 영상은 쓰지 않는다.")
    elif kind == "GRAPHICS_PROFILE":
        ins.append("수치가 등장하면 chart 또는 motion graphic으로 보강한다.")
    elif kind == "AUDIO_PROFILE":
        ins.append("중요 CTA 직전 불필요한 오디오 에너지를 낮춰 메시지 집중도를 확보한다.")
    elif kind == "RETENTION_PATTERN":
        ins.append("도입부에 시청 이유를 명확히 두고, 중반 정보 밀도를 유지한다.")
        con.append("리텐션 수치는 우리 Analytics로만 검증한다(레퍼런스만으로 단정 금지).")
    elif kind == "SUBTITLE_PROFILE":
        ins.append("핵심 단어를 하이라이트하고 한 화면 자막 길이를 짧게 유지한다.")
    elif kind == "VOICE_PROFILE":
        ins.append("문장 사이 짧은 포즈로 가독성을 확보하되 과도한 속도 변화는 피한다.")
    elif kind == "WRITING_PROFILE":
        if merged.get("opening_type") == "STAT":
            pos.append("데이터로 여는 오프닝")
        ins.append("짧은 문장과 직접 화법을 섞어 정보 밀도를 유지한다.")
        con.append("원문 표현을 그대로 복사하지 않는다(특징만 재현).")
    elif kind == "STORY_PROFILE":
        beats = merged.get("common_beats", [])
        if beats:
            ins.append("스토리 비트 순서 예: " + " → ".join(beats[:6]))
    elif kind == "FACTS":
        con.append("외부 URL의 수치·주장은 Fact Checker 통과 전까지 사실로 쓰지 않는다.")
    elif kind == "KNOWLEDGE":
        ins.append("핵심 개념을 먼저 정의하고 예시로 뒷받침한다.")
    elif kind == "GITHUB_ANALYSIS":
        con.append("코드 라이선스는 콘텐츠 라이선스가 아니다 — 레포의 미디어를 그대로 쓰지 않는다.")
    elif kind == "COMPETITOR_ANALYSIS":
        pos.append("경쟁 채널이 자주 쓰는 각도(관찰용, 모방 아님)")

    return {"instructions": ins, "constraints": con,
            "positive_patterns": pos, "negative_patterns": neg}


def _merge_features(kind: str, per_ref: list[dict]) -> dict:
    """Combine the same-kind analysis across references into a summary +
    consistency score."""
    if not per_ref:
        return {"_consistency": 0.0}
    merged: dict = {}
    if kind == "HOOK_PATTERN":
        tags = Counter(t for d in per_ref for t in (d.get("abstracted") or []))
        n = len(per_ref)
        common = [t for t, c in tags.items() if c >= max(2, n * 0.5) and t != "UNKNOWN"]
        merged["common_hook_tags"] = common
        merged["_consistency"] = round(sum(tags[t] for t in common) / max(1, n * max(1, len(common) or 1)), 3) if common else 0.2
    elif kind == "STORY_PROFILE":
        beats = Counter(tuple(d.get("beats_used") or []) for d in per_ref if d.get("beats_used"))
        top = beats.most_common(1)
        merged["common_beats"] = list(top[0][0]) if top and top[0][0] != ("UNKNOWN",) else []
        merged["_consistency"] = round((top[0][1] / len(per_ref)) if top else 0.0, 3)
    elif kind in ("EDITING_PROFILE",):
        vals = [d.get("scene_duration_mean") for d in per_ref if isinstance(d.get("scene_duration_mean"), (int, float))]
        if vals:
            merged["scene_duration_mean"] = round(sum(vals) / len(vals), 2)
            spread = (max(vals) - min(vals)) / (max(vals) or 1)
            merged["_consistency"] = round(max(0.0, 1.0 - spread), 3)
        else:
            merged["_consistency"] = 0.3
    elif kind == "WRITING_PROFILE":
        ot = Counter(d.get("opening_type") for d in per_ref if d.get("opening_type"))
        if ot:
            merged["opening_type"] = ot.most_common(1)[0][0]
            merged["_consistency"] = round(ot.most_common(1)[0][1] / len(per_ref), 3)
        else:
            merged["_consistency"] = 0.3
    else:
        merged["_consistency"] = 0.55 if len(per_ref) >= 2 else 0.3
    return merged


def _confidence(*, sample_size: int, source_diversity: float, quality: float, consistency: float) -> float:
    size_term = min(1.0, sample_size / 10.0)
    return round(max(0.0, min(0.95,
        0.35 * size_term + 0.25 * source_diversity + 0.20 * quality + 0.20 * consistency)), 3)


def _cap_status(sample_size: int, confidence: float) -> str:
    s = get_settings()
    if sample_size <= 1:
        return s.learning_single_source_max_status         # OBSERVED / EXPERIMENTAL
    if sample_size < s.learning_min_blueprint_sample:
        return "EXPERIMENTAL"
    if confidence >= 0.75:
        return "CANDIDATE"
    if confidence >= 0.5:
        return "EXPERIMENTAL"
    return "OBSERVED"


def distill(db: Session, *, workspace_id: str | None, brand_id: str | None, channel_id: str | None,
            agent_type: str, kind: str,
            evidence: list[dict], platforms: list[str] | None = None,
            content_types: list[str] | None = None, topic_clusters: list[str] | None = None,
            quality: float = 0.5) -> PromptBlueprint | None:
    """evidence: [{reference_id, data, source_domain, evidence_type}]. Returns a
    PromptBlueprint (status capped by sample size) with traceable evidence rows."""
    per_ref = [e.get("data") or {} for e in evidence]
    merged = _merge_features(kind, per_ref)
    lines = _blueprint_lines(agent_type, kind, merged)
    if not any(lines.values()):
        return None

    domains = {e.get("source_domain") or e.get("reference_id") for e in evidence}
    sample_size = len({e.get("reference_id") for e in evidence if e.get("reference_id")}) or len(evidence)
    source_diversity = round(min(1.0, len(domains) / max(1, sample_size)), 3)
    consistency = float(merged.get("_consistency", 0.0))
    confidence = _confidence(sample_size=sample_size, source_diversity=source_diversity,
                             quality=quality, consistency=consistency)
    status = _cap_status(sample_size, confidence)

    bp = PromptBlueprint(
        workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id,
        agent_type=agent_type, purpose=f"{kind} distilled guidance",
        instructions=lines["instructions"], constraints=lines["constraints"],
        positive_patterns=lines["positive_patterns"], negative_patterns=lines["negative_patterns"],
        platforms=platforms or [], content_types=content_types or [],
        topic_clusters=topic_clusters or [],
        quality_score=round(quality, 3), confidence=confidence, sample_size=sample_size,
        source_diversity=source_diversity, consistency=round(consistency, 3),
        status=status, version=1,
    )
    db.add(bp)
    db.flush()
    for e in evidence:
        db.add(PromptBlueprintEvidence(
            blueprint_id=bp.id, workspace_id=workspace_id,
            evidence_type=e.get("evidence_type", "EXTERNAL_REFERENCE"),
            reference_id=e.get("reference_id"), dataset_record_id=e.get("dataset_record_id"),
            observation=e.get("observation", f"{kind} feature observed")[:1000],
            weight=float(e.get("weight", 1.0)),
        ))
    db.flush()
    return bp


def add_internal_evidence(db: Session, blueprint_id: str, *, campaign_id: str,
                          metric_delta: dict, observation: str, weight: float = 1.5) -> None:
    """Wire our own Analytics result to a blueprint (spec §Y — internal data
    outranks external references)."""
    bp = db.get(PromptBlueprint, blueprint_id)
    if bp is None:
        return
    db.add(PromptBlueprintEvidence(
        blueprint_id=blueprint_id, workspace_id=bp.workspace_id,
        evidence_type="INTERNAL_CONTENT", campaign_id=campaign_id,
        observation=observation[:1000], weight=weight, metric_delta=metric_delta or {},
    ))
    bp.sample_size = (bp.sample_size or 0) + 1
    bp.confidence = min(0.97, round(bp.confidence + 0.05, 3))
    db.flush()


def advance_status(db: Session, blueprint_id: str, to_status: str, *, actor: str = "system",
                   reason: str = "") -> dict:
    bp = db.get(PromptBlueprint, blueprint_id)
    if bp is None:
        return {"ok": False, "error": "not found"}
    to_status = to_status.upper()
    if to_status not in BLUEPRINT_STATUS:
        return {"ok": False, "error": f"unknown status {to_status}"}
    if not valid_transition(bp.status, to_status):
        return {"ok": False, "error": f"invalid transition {bp.status} -> {to_status}"}
    # single-source guard: cannot exceed the capped status without more evidence
    if _ORDER.get(to_status, 99) > _ORDER.get("EXPERIMENTAL", 1) and (bp.sample_size or 0) <= 1:
        return {"ok": False, "error": "single-reference blueprint cannot advance past EXPERIMENTAL"}
    # promotion needs a human or a validated experiment (AUTO_PROMOTE is off)
    if to_status == "PROMOTED":
        s = get_settings()
        if not s.auto_promote_learned_prompts and actor == "system" and not reason.startswith("EXPERIMENT_VALIDATED"):
            return {"ok": False, "error": "promotion requires user approval or a VALIDATED experiment"}
    bp.status = to_status
    db.flush()
    return {"ok": True, "status": bp.status}


def rollback(db: Session, blueprint_id: str, *, actor: str = "user") -> dict:
    bp = db.get(PromptBlueprint, blueprint_id)
    if bp is None:
        return {"ok": False, "error": "not found"}
    target = "VALIDATED" if bp.status == "PROMOTED" else "DEPRECATED"
    bp.status = target
    db.flush()
    return {"ok": True, "status": bp.status}
