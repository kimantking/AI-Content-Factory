from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.autopilot.platform_select import select_platforms
from app.db.models import TopicCandidate


@dataclass
class AutopilotContext:
    candidate_id: str
    run_id: str
    topic: str
    angle: str
    objective: str
    opportunity_score: float
    platform_scores: dict
    trend_evidence: dict
    audience: str
    recommended_platforms: list[dict]
    recommended_content_types: list[str]
    production_profile: str
    recommended_hook_direction: str
    estimated_cost: float
    risk_level: str
    risk_categories: list[str]
    deadline: str | None
    source_ids: list[str]
    decision_reason: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_context(session, cand: TopicCandidate, *, objective: str) -> AutopilotContext:
    platforms = select_platforms(session, cand)
    expl = cand.explanation or {}
    score = expl.get("score", {})
    hook_dir = {
        "BREAKING": "긴급성 + 호기심", "FAST_TREND": "위협 + 호기심",
        "EVERGREEN": "문제 제기 + 약속", "SEASONAL": "타이밍 강조",
    }.get(cand.trend_type, "위협 + 호기심")
    return AutopilotContext(
        candidate_id=cand.id, run_id=cand.run_id, topic=cand.topic, angle=cand.angle,
        objective=objective, opportunity_score=cand.opportunity_score or 0.0,
        platform_scores=cand.platform_scores or {},
        trend_evidence={"trend_type": cand.trend_type, "trend_score": cand.trend_score,
                        "velocity": cand.velocity_score, "acceleration": cand.acceleration_score,
                        "dedup_status": cand.dedup_status, "raw_topic": expl.get("raw_topic")},
        audience=cand.target_audience or "일반 대중",
        recommended_platforms=platforms,
        recommended_content_types=sorted({p["content_type"] for p in platforms}),
        production_profile=expl.get("production_profile", "STANDARD"),
        recommended_hook_direction=hook_dir,
        estimated_cost=cand.estimated_cost,
        risk_level=cand.risk_level, risk_categories=cand.risk_categories or [],
        deadline=cand.expires_at.isoformat() if cand.expires_at else None,
        source_ids=cand.source_ids or [],
        decision_reason=score.get("reasons", []),
    )
