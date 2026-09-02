from __future__ import annotations

import pytest

from app.autopilot.config import (
    HardRuleViolation,
    apply_config,
    enforce_hard_rules,
    risk_rank,
    topic_blocked,
)
from app.autopilot.scoring import objective_weights, platform_scores, score_opportunity
from app.autopilot import signals
from app.db.base import session_scope
from app.trends.capabilities import load_trend_capabilities
from app.trends.registry import all_trend_sources


# ---- trend capability registry --------------------------------------- #

def test_trend_capability_registry_is_honest():
    caps = load_trend_capabilities()
    assert set(caps) == set(all_trend_sources())
    assert caps["google_trends"].auth_status == "APPROVAL_REQUIRED"      # not faked AVAILABLE
    assert caps["tiktok_trends"].auth_status == "UNAVAILABLE"
    assert caps["own_analytics"].auth_status == "AVAILABLE"
    for c in caps.values():
        assert c.last_verified_at


# ---- signal sub-scores --------------------------------------------- #

def test_velocity_and_trend_status():
    breakout = {"interest_series": {"1h": 0.9, "6h": 0.85, "24h": 0.55, "3d": 0.3, "7d": 0.18, "30d": 0.1}}
    declining = {"interest_series": {"1h": 0.2, "6h": 0.24, "24h": 0.32, "3d": 0.45, "7d": 0.62, "30d": 0.8}}
    assert signals.velocity_score(breakout) > 70
    assert signals.velocity_score(declining) < 40
    assert signals.trend_status(breakout) in ("BREAKOUT", "ACCELERATING")
    assert signals.trend_status(declining) == "DECLINING"


def test_risk_classifier():
    lvl, cats, sc = signals.risk_classify("독감 예방접종 언제 맞아야 효과적일까", {"risk_hint": "MEDICAL"})
    assert lvl in ("HIGH", "MEDIUM") and "MEDICAL" in cats and sc > 30
    lvl2, cats2, _ = signals.risk_classify("다음 총선 주요 쟁점", {"risk_hint": "LOW"})
    assert lvl2 == "HIGH" and "ELECTION" in cats2
    lvl3, _c, _s = signals.risk_classify("혼자 사는 사람을 위한 10분 요리", {"risk_hint": "LOW"})
    assert lvl3 == "LOW"


def test_natural_content_and_fact_availability():
    good = signals.natural_content_score("전세사기 피하는 계약서 체크리스트", {"evergreen": True})
    bare = signals.natural_content_score("AI", {})
    assert good > bare + 20
    assert signals.fact_availability_score(0) < 20
    assert signals.fact_availability_score(10) >= 60


# ---- opportunity scoring ---------------------------------------- #

def test_objective_weights_differ():
    assert objective_weights("PROFIT") != objective_weights("VIEWS")
    assert "profit" in objective_weights("PROFIT")
    assert "trend" in objective_weights("VIEWS")


def test_bad_dimensions_are_inverted():
    # high competition / risk / cost should LOWER the score
    low = score_opportunity({"trend": 70, "competition": 95, "risk": 90}, objective="BALANCED")
    high = score_opportunity({"trend": 70, "competition": 10, "risk": 5}, objective="BALANCED")
    assert high["opportunity_score"] > low["opportunity_score"]


def test_dedup_penalty_applied():
    a = score_opportunity({"trend": 80, "historical": 70}, objective="BALANCED")
    b = score_opportunity({"trend": 80, "historical": 70}, objective="BALANCED", dedup_penalty=-30)
    assert b["opportunity_score"] < a["opportunity_score"] - 10


def test_platform_scores_tilt():
    dims = {"velocity": 90, "fact_availability": 90, "natural_content": 70, "trend": 80}
    ps = platform_scores(dims, objective="BALANCED", platforms=["tiktok", "linkedin"])
    # tiktok rewards velocity, linkedin rewards fact_availability — both should be high but different
    assert ps["tiktok"] > 0 and ps["linkedin"] > 0 and ps["tiktok"] != ps["linkedin"]


# ---- hard rules ------------------------------------------------ #

def test_hard_rules_block_ai_not_user():
    with pytest.raises(HardRuleViolation):
        enforce_hard_rules({"autopilot_daily_hard_budget_usd": 9999}, actor="ai")
    enforce_hard_rules({"autopilot_daily_hard_budget_usd": 9999}, actor="user")   # ok


def test_apply_config_gate_and_versioning(_autopilot_defaults):
    with session_scope() as s, pytest.raises(HardRuleViolation):
        apply_config(s, {"autopilot_daily_post_limit": 999}, actor="ai")
    with session_scope() as s:
        v = apply_config(s, {"autopilot_min_opportunity_score": 60.0}, actor="ai")   # soft key ok
        assert v.startswith("v")
    assert _autopilot_defaults.autopilot_min_opportunity_score == 60.0


def test_topic_blocked(_autopilot_defaults):
    _autopilot_defaults.autopilot_blocked_keywords = ["코인"]
    assert topic_blocked("비트코인 반감기 전망") is not None
    assert topic_blocked("전세사기 피하는 법") is None


def test_risk_rank_order():
    assert risk_rank("LOW") < risk_rank("MEDIUM") < risk_rank("HIGH") < risk_rank("CRITICAL")
