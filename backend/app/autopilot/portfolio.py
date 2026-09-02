from __future__ import annotations

from app.config import get_settings
from app.db.models import AutopilotDecision, TopicCandidate

PORTFOLIO_TYPES = ["CORE", "TREND", "EVERGREEN", "REVENUE", "EXPERIMENT"]
_DEFAULT_RATIO = {"CORE": 0.4, "TREND": 0.2, "EVERGREEN": 0.2, "REVENUE": 0.1, "EXPERIMENT": 0.1}
PRODUCTION_PROFILES = ["FAST", "STANDARD", "PREMIUM"]


def _classify(cand: TopicCandidate) -> str:
    if cand.trend_type in ("BREAKING", "FAST_TREND") and (cand.velocity_score or 0) >= 60:
        return "TREND"
    if cand.trend_type == "EVERGREEN":
        return "EVERGREEN"
    if (cand.revenue_score or 0) >= 65 or (cand.profit_score or 0) >= 70:
        return "REVENUE"
    return "CORE"


def _profile_for(cand: TopicCandidate, budget_ok_premium: bool) -> str:
    if cand.trend_type in ("BREAKING", "FAST_TREND"):
        return "FAST"
    if budget_ok_premium and (cand.opportunity_score or 0) >= 80 and (cand.revenue_score or 0) >= 60:
        return "PREMIUM"
    return "STANDARD"


def _decide(session, run_id: str, cand_id: str | None, dtype: str, selected: bool,
            reason: str, scores: dict | None = None) -> None:
    session.add(AutopilotDecision(
        run_id=run_id, candidate_id=cand_id, decision_type=dtype, selected=selected,
        reason=reason, input_scores=scores or {},
        config_version=get_settings().autopilot_config_version,
    ))


def select_portfolio(session, run_id: str, *, objective: str, daily_budget: float,
                     experiment_ratio: float) -> list[TopicCandidate]:
    """Pick today's content: not just top-N. Portfolio mix + diversity guard +
    dynamic count + non-uniform budget allocation + a trend reserve."""
    s = get_settings()
    # resume path: this run already has selections — return them, don't re-pick
    already = (session.query(TopicCandidate)
               .filter(TopicCandidate.run_id == run_id,
                       TopicCandidate.status.in_(["SELECTED", "PRODUCING", "SCHEDULED"]))
               .order_by(TopicCandidate.opportunity_score.desc()).all())
    if already:
        return already

    pool = (session.query(TopicCandidate).filter_by(run_id=run_id, status="SCORED")
            .order_by(TopicCandidate.opportunity_score.desc()).all())
    strong = [c for c in pool if (c.opportunity_score or 0) >= s.autopilot_min_opportunity_score
              and (c.fact_availability_score or 0) >= 20]

    # dynamic count: bounded by min/max AND strong-opportunity availability
    want = min(s.autopilot_daily_content_max, max(s.autopilot_daily_content_min, len(strong)))
    if not strong:
        for c in pool[:1]:
            _decide(session, run_id, c.id, "count", False, "no strong opportunities today")
        session.flush()
        return []

    reserve = round(daily_budget * s.autopilot_trend_reserve_ratio, 4)
    spendable = round(daily_budget - reserve, 4)

    selected: list[TopicCandidate] = []
    used_clusters: dict[str, int] = {}
    spent = 0.0
    n_experiment = 0
    for cand in strong:
        if len(selected) >= want:
            break
        ptype = _classify(cand)
        # experiment slot
        if n_experiment < max(1, round(want * experiment_ratio)) and cand.dedup_status in ("NEW", "NEW_ANGLE") \
                and (cand.opportunity_score or 0) < 78:
            ptype = "EXPERIMENT"

        # diversity guard: don't let one cluster dominate
        cid = cand.topic_cluster_id or cand.id
        if used_clusters.get(cid, 0) >= max(1, want // 2) and len(strong) > want:
            _decide(session, run_id, cand.id, "diversity", False,
                    f"cluster {cid} already well represented")
            continue

        # budget allocator: higher opportunity -> more budget; experiment -> less
        weight = 0.6 + (cand.opportunity_score or 50) / 100.0
        if ptype == "EXPERIMENT":
            weight *= 0.5
        if ptype == "EVERGREEN":
            weight *= 0.85
        alloc = round(min(spendable - spent, max(cand.estimated_cost, 0.2) * weight * 1.5), 4)
        if alloc < cand.estimated_cost * 0.8 or spent + cand.estimated_cost > spendable:
            _decide(session, run_id, cand.id, "budget", False,
                    f"insufficient budget (need ~{cand.estimated_cost}, left {round(spendable - spent,3)})")
            continue

        premium_ok = (spendable - spent) > cand.estimated_cost * 3
        profile = _profile_for(cand, premium_ok)
        if profile == "PREMIUM":
            _decide(session, run_id, cand.id, "premium", True,
                    "budget allocator approved PREMIUM", {"opportunity": cand.opportunity_score})

        cand.status = "SELECTED"
        cand.portfolio_type = ptype
        cand.explanation = {**(cand.explanation or {}), "production_profile": profile,
                            "budget_allocation": alloc, "portfolio_type": ptype}
        spent += cand.estimated_cost
        used_clusters[cid] = used_clusters.get(cid, 0) + 1
        if ptype == "EXPERIMENT":
            n_experiment += 1
        selected.append(cand)
        _decide(session, run_id, cand.id, "selection", True,
                f"{ptype} pick, opp={cand.opportunity_score}", cand.explanation.get("score", {}))

    _decide(session, run_id, None, "count", True,
            f"selected {len(selected)}/{want} (min {s.autopilot_daily_content_min}, "
            f"max {s.autopilot_daily_content_max}); reserve ${reserve}")
    session.flush()
    return selected
