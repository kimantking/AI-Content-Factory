from __future__ import annotations

import uuid

import pytest

from app.autopilot.dedup import duplicate_status
from app.autopilot.historical import fatigue_score
from app.autopilot.portfolio import select_portfolio
from app.autopilot.scoring import score_opportunity
from app.db.base import session_scope
from app.db.models import (
    Campaign,
    LearningMemory,
    PlatformContent,
    TopicCandidate,
)

pytestmark = pytest.mark.integration


# ---- OPPORTUNITY: PROFIT objective can prefer the lower-trend candidate ---- #

def test_profit_objective_prefers_efficient_candidate():
    # A: huge trend, but expensive + crowded + risky
    A = {"trend": 96, "velocity": 90, "acceleration": 85, "freshness": 80,
         "historical": 60, "audience_fit": 60, "revenue": 40, "profit": 30,
         "competition": 92, "saturation": 90, "originality": 35,
         "fact_availability": 55, "production_cost": 25, "difficulty": 85,
         "natural_content": 50, "fatigue": 30, "risk": 70}
    # B: mid trend, cheap, low competition, high margin
    B = {"trend": 62, "velocity": 55, "acceleration": 50, "freshness": 55,
         "historical": 70, "audience_fit": 72, "revenue": 78, "profit": 85,
         "competition": 28, "saturation": 25, "originality": 80,
         "fact_availability": 80, "production_cost": 88, "difficulty": 25,
         "natural_content": 78, "fatigue": 15, "risk": 12}

    views_a = score_opportunity(A, objective="VIEWS")["opportunity_score"]
    views_b = score_opportunity(B, objective="VIEWS")["opportunity_score"]
    profit_a = score_opportunity(A, objective="PROFIT")["opportunity_score"]
    profit_b = score_opportunity(B, objective="PROFIT")["opportunity_score"]

    assert views_a > views_b               # VIEWS: the viral one wins
    assert profit_b > profit_a             # PROFIT: the efficient one wins


def test_objective_changes_ranking():
    cands = {
        "viral": {"trend": 95, "velocity": 92, "acceleration": 88, "freshness": 82,
                  "historical": 55, "audience_fit": 55, "revenue": 35, "profit": 30,
                  "competition": 60, "originality": 40, "fact_availability": 50,
                  "natural_content": 45, "fatigue": 30, "risk": 25},
        "brandy": {"trend": 50, "velocity": 45, "acceleration": 40, "freshness": 60,
                   "historical": 78, "audience_fit": 80, "revenue": 50, "profit": 55,
                   "competition": 35, "originality": 85, "fact_availability": 90,
                   "natural_content": 88, "fatigue": 12, "risk": 8},
        "earner": {"trend": 60, "velocity": 55, "acceleration": 50, "freshness": 55,
                   "historical": 70, "audience_fit": 70, "revenue": 90, "profit": 82,
                   "competition": 40, "originality": 60, "fact_availability": 75,
                   "natural_content": 65, "fatigue": 20, "risk": 15},
    }
    def rank(obj):
        return sorted(cands, key=lambda k: score_opportunity(cands[k], objective=obj)["opportunity_score"],
                      reverse=True)
    assert rank("VIEWS")[0] == "viral"
    assert rank("BRAND")[0] == "brandy"
    assert rank("REVENUE")[0] == "earner"


# ---- DUPLICATE guard ---------------------------------------------- #

def test_duplicate_guard_against_recent_publishes():
    cid = str(uuid.uuid4())
    with session_scope() as s:
        s.add(Campaign(id=cid, topic="AI로 사라질 가능성이 높은 직업",
                       platforms=["youtube_shorts"], status="SUCCESS"))
        s.flush()
        s.add(PlatformContent(campaign_id=cid, platform="youtube_shorts",
                              content_type="SHORT_VIDEO", title="x", status="SUCCESS"))
    with session_scope() as s:
        near, _m = duplicate_status(s, "인공지능이 대체할 일자리 전망", "직업 순위 나열")
        far, _m2 = duplicate_status(s, "혼자 사는 사람을 위한 10분 요리", "간단 레시피")
    assert near in ("DUPLICATE", "SIMILAR", "NEW_ANGLE")
    assert far == "NEW"


# ---- FATIGUE ------------------------------------------------------ #

def test_fatigue_score_uses_phase3_memory():
    with session_scope() as s:
        assert fatigue_score(s, "ai-job") <= 25
        s.add(LearningMemory(memory_type="TOPIC", dimension="fatigue", topic_cluster="ai-job",
                             statement="fatigue", confidence=0.8, sample_size=6, status="MODERATE"))
    with session_scope() as s:
        assert fatigue_score(s, "ai-job") >= 60


# ---- DIVERSITY + BUDGET (portfolio) ----------------------------- #

def _mk_candidates(run_id: str, specs: list[dict]) -> None:
    with session_scope() as s:
        for sp in specs:
            s.add(TopicCandidate(
                run_id=run_id, topic=sp["topic"], angle="a",
                topic_cluster_id=sp["cluster"], status="SCORED",
                opportunity_score=sp["opp"], estimated_cost=sp.get("cost", 0.3),
                fact_availability_score=80, trend_type=sp.get("ttype", "NORMAL_TREND"),
                dedup_status="NEW", risk_level="LOW",
                platform_scores={"youtube_shorts": sp["opp"], "tiktok": sp["opp"] - 5},
            ))


def test_portfolio_diversity_guard(_autopilot_defaults):
    _autopilot_defaults.autopilot_daily_content_max = 4
    _autopilot_defaults.autopilot_min_opportunity_score = 50
    run_id = str(uuid.uuid4())
    _mk_candidates(run_id, [
        {"topic": "ai a", "cluster": "ai-job", "opp": 90},
        {"topic": "ai b", "cluster": "ai-job", "opp": 88},
        {"topic": "ai c", "cluster": "ai-job", "opp": 86},
        {"topic": "ai d", "cluster": "ai-job", "opp": 84},
        {"topic": "cook a", "cluster": "cooking", "opp": 72},
        {"topic": "money a", "cluster": "finance", "opp": 70},
    ])
    with session_scope() as s:
        picked = select_portfolio(s, run_id, objective="BALANCED",
                                  daily_budget=5.0, experiment_ratio=0.0)
        clusters = [c.topic_cluster_id for c in picked]
    assert len(picked) >= 2
    assert clusters.count("ai-job") <= 2               # not all from one cluster


def test_portfolio_budget_hard_limit(_autopilot_defaults):
    _autopilot_defaults.autopilot_daily_content_max = 5
    _autopilot_defaults.autopilot_min_opportunity_score = 50
    run_id = str(uuid.uuid4())
    _mk_candidates(run_id, [
        {"topic": "t1", "cluster": "c1", "opp": 85, "cost": 2.5},
        {"topic": "t2", "cluster": "c2", "opp": 82, "cost": 2.5},
        {"topic": "t3", "cluster": "c3", "opp": 80, "cost": 2.5},
        {"topic": "t4", "cluster": "c4", "opp": 78, "cost": 2.5},
    ])
    with session_scope() as s:
        picked = select_portfolio(s, run_id, objective="BALANCED",
                                  daily_budget=4.0, experiment_ratio=0.0)   # reserve 0.8 -> spendable 3.2
        spent = sum(c.estimated_cost for c in picked)
    assert spent <= 3.2 + 1e-6                        # never exceeds spendable budget
    assert len(picked) < 4                            # cannot afford all
