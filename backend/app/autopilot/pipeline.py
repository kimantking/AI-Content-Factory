from __future__ import annotations

import json
from datetime import datetime, timezone

from app.autopilot.config import topic_blocked
from app.autopilot.dedup import assign_topic_cluster, dedup_penalty, duplicate_status
from app.autopilot.historical import (
    audience_fit_score,
    fatigue_score,
    historical_score,
    revenue_score,
)
from app.autopilot.scoring import platform_scores, score_opportunity
from app.autopilot import signals
from app.config import get_settings
from app.db.models import RawTrendEvent, TopicCandidate, TopicRejection
# LLM access via the Model Execution Gateway (AUDIT-P8-001) — no direct provider here

_VIDEO_PLATFORMS = ["youtube_shorts", "tiktok", "instagram_reel", "youtube_long"]
_ALL_PLATFORMS = _VIDEO_PLATFORMS + ["instagram_carousel", "threads", "x", "pinterest",
                                     "linkedin", "naver_blog"]


def _llm_json(task: str, ctx: dict) -> dict:
    from app.agents.model_gateway import routed_complete

    resp = routed_complete(agent_name="Strategist", task=task,
                           system=f"autopilot:{task}",
                           user=json.dumps(ctx, ensure_ascii=False), context=ctx)
    try:
        return json.loads(resp.text)
    except ValueError:
        return {}


def _permanent_blocks(session) -> set[str]:
    return {r.topic_cluster_id for r in session.query(TopicRejection).filter_by(scope="PERMANENT")
            if r.topic_cluster_id}


# --------------------------------------------------------------------------- #

def extract_candidates(session, run_id: str) -> list[TopicCandidate]:
    """RawTrendEvent -> refined TopicCandidate angles + cluster + dedup status."""
    s = get_settings()
    events = session.query(RawTrendEvent).filter_by(run_id=run_id).all()
    perm = _permanent_blocks(session)
    out: list[TopicCandidate] = []
    seen_topic_angle: set[tuple[str, str]] = set()

    for ev in events:
        sig = ev.engagement_signals or {}
        data = _llm_json("topic_extract", {
            "raw_topic": ev.raw_topic, "cluster_hint": sig.get("cluster_hint"),
            "country": ev.country, "audience_hint": "일반 대중 / 커리어 관심층",
        })
        for c in (data.get("candidates") or [])[:2]:
            topic = (c.get("topic") or ev.raw_topic).strip()
            angle = (c.get("angle") or "").strip()
            if (topic, angle) in seen_topic_angle:
                continue
            seen_topic_angle.add((topic, angle))

            blocked = topic_blocked(topic)
            cluster_id, _emb = assign_topic_cluster(session, topic)
            if cluster_id in perm:
                blocked = blocked or f"cluster:{cluster_id}"

            dup, dup_meta = duplicate_status(session, topic, angle)
            ttype = signals.trend_type(sig)
            ttl = signals.ttl_for(ttype)

            cand = TopicCandidate(
                run_id=run_id, topic=topic, angle=angle,
                topic_cluster_id=cluster_id, target_audience=c.get("audience", ""),
                country=ev.country, language=ev.language, source_ids=[ev.source_id],
                expires_at=datetime.now(timezone.utc) + ttl, trend_type=ttype,
                dedup_status=dup, status="BLOCKED" if blocked else "CANDIDATE",
                explanation={"raw_topic": ev.raw_topic, "dup": dup_meta,
                             "blocked_by": blocked},
                stage=1,
            )
            session.add(cand)
            out.append(cand)
    session.flush()
    return out


def prescore_stage1(session, run_id: str) -> list[TopicCandidate]:
    """Cheap pre-score: trend / freshness / duplicate / basic competition only."""
    s = get_settings()
    cands = (session.query(TopicCandidate)
             .filter_by(run_id=run_id).filter(TopicCandidate.status == "CANDIDATE").all())
    ev_by_source = {e.source_id: e for e in session.query(RawTrendEvent).filter_by(run_id=run_id)}
    scored = []
    for cand in cands:
        ev = ev_by_source.get((cand.source_ids or [None])[0])
        sig = (ev.engagement_signals if ev else {}) or {}
        metrics = (ev.source_metrics if ev else {}) or {}
        v = signals.velocity_score(sig)
        a = signals.acceleration_score(sig)
        f = signals.freshness_score(sig)
        comp = signals.competition_score(sig, metrics)
        series = sig.get("interest_series", {})
        trend = round((series.get("6h", 0) + series.get("24h", 0)) / 2 * 100, 2) if series else 50.0
        cheap = round(0.35 * trend + 0.25 * v + 0.15 * a + 0.15 * f + 0.10 * (100 - comp)
                      + dedup_penalty(cand.dedup_status), 2)
        cand.trend_score = trend
        cand.velocity_score = v
        cand.acceleration_score = a
        cand.freshness_score = f
        cand.competition_score = comp
        cand.opportunity_score = max(0.0, cheap)   # provisional
        cand.status = "PRESCORED"
        cand.stage = 1
        scored.append((cheap, cand))
    scored.sort(key=lambda x: x[0], reverse=True)
    keep = [c for _s, c in scored[: s.autopilot_stage1_keep]]
    for _s, c in scored[s.autopilot_stage1_keep:]:
        c.status = "REJECTED"
        c.explanation = {**(c.explanation or {}), "rejected": "stage1 cutoff"}
    session.flush()
    return keep


def fullscore_stage2(session, run_id: str, *, objective: str) -> list[TopicCandidate]:
    """Expensive score: research precheck + historical + revenue + originality +
    risk + cost + natural feasibility -> Opportunity Score + platform scores."""
    s = get_settings()
    cands = (session.query(TopicCandidate)
             .filter_by(run_id=run_id).filter(TopicCandidate.status == "PRESCORED").all())
    ev_by_source = {e.source_id: e for e in session.query(RawTrendEvent).filter_by(run_id=run_id)}

    scored = []
    for cand in cands:
        ev = ev_by_source.get((cand.source_ids or [None])[0])
        sig = (ev.engagement_signals if ev else {}) or {}
        metrics = (ev.source_metrics if ev else {}) or {}

        # research / fact precheck
        fa = signals.fact_availability_score(metrics.get("result_count", 0))
        if fa < 20:
            cand.status = "REJECTED"
            cand.fact_availability_score = fa
            cand.explanation = {**(cand.explanation or {}), "rejected": "LOW_FACT_AVAILABILITY"}
            continue

        hist, hist_n, hist_conf = historical_score(session, cand.topic)
        aud = audience_fit_score(session, cand.topic)
        rev, rev_est = revenue_score(session, cand.topic)
        fat = fatigue_score(session, cand.topic_cluster_id)
        risk_level, risk_cats, risk_sc = signals.risk_classify(cand.topic, sig)
        diff = signals.difficulty_class(cand.topic, sig)
        diff_sc = {"LOW": 15, "MEDIUM": 40, "HIGH": 70, "VERY_HIGH": 92}[diff]
        nat = signals.natural_content_score(cand.topic, sig)
        est_cost, cost_sc = signals.production_cost_estimate(cand.topic, sig)
        orig = _llm_json("originality", {"topic": cand.topic, "angle": cand.angle,
                                         "competition_hint": sig.get("competition_hint", "mid")})
        orig_sc = float(orig.get("originality_score", 55.0))
        sat = signals.saturation_score(sig, metrics)
        profit_sc = round(max(0.0, min(100.0, rev * 0.6 + cost_sc * 0.4)), 2)

        dims = {
            "trend": cand.trend_score, "velocity": cand.velocity_score,
            "acceleration": cand.acceleration_score, "freshness": cand.freshness_score,
            "historical": hist, "audience_fit": aud, "revenue": rev, "profit": profit_sc,
            "competition": cand.competition_score, "saturation": sat, "originality": orig_sc,
            "fact_availability": fa, "production_cost": cost_sc, "difficulty": diff_sc,
            "natural_content": nat, "fatigue": fat, "risk": risk_sc,
        }
        res = score_opportunity(dims, objective=objective,
                                dedup_penalty=dedup_penalty(cand.dedup_status))
        psc = platform_scores(dims, objective=objective, platforms=_ALL_PLATFORMS,
                              dedup_penalty=dedup_penalty(cand.dedup_status))

        cand.historical_score = hist
        cand.audience_fit_score = aud
        cand.revenue_score = rev
        cand.profit_score = profit_sc
        cand.saturation_score = sat
        cand.originality_score = orig_sc
        cand.fact_availability_score = fa
        cand.production_cost_score = cost_sc
        cand.production_difficulty_score = diff_sc
        cand.natural_content_score = nat
        cand.fatigue_score = fat
        cand.risk_score = risk_sc
        cand.risk_level = risk_level
        cand.risk_categories = risk_cats
        cand.estimated_cost = est_cost
        cand.platform_scores = psc
        cand.opportunity_score = res["opportunity_score"]
        cand.opportunity_formula_version = res["formula_version"]
        cand.confidence = round(min(0.95, 0.4 + 0.05 * hist_n + (0.1 if fa >= 65 else 0)), 3)
        cand.explanation = {**(cand.explanation or {}), "score": res,
                            "revenue_is_estimate": rev_est, "historical_n": hist_n}
        cand.status = "SCORED"
        cand.stage = 2
        scored.append((res["opportunity_score"], cand))

    scored.sort(key=lambda x: x[0], reverse=True)
    final = [c for _s, c in scored[: s.autopilot_stage2_keep]]
    for _s, c in scored[s.autopilot_stage2_keep:]:
        c.status = "REJECTED"
        c.explanation = {**(c.explanation or {}), "rejected": "stage2 cutoff"}
    session.flush()
    return final


def run_candidate_pipeline(session, run_id: str, *, objective: str) -> dict:
    extracted = extract_candidates(session, run_id)
    stage1 = prescore_stage1(session, run_id)
    final = fullscore_stage2(session, run_id, objective=objective)
    return {
        "extracted": len(extracted),
        "stage1_kept": len(stage1),
        "final": len(final),
        "blocked": sum(1 for c in extracted if c.status == "BLOCKED"),
    }
