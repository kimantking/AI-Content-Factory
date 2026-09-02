from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db.base import session_scope
from app.db.models import Campaign, CostLog, RevenueEntry
from app.db.models_mb import Channel
from app.mb import monetization as M


def test_estimate_and_actual_revenue_never_summed(workspace_a):
    ch = workspace_a["channel1_id"]
    with session_scope() as db:
        cid = str(uuid.uuid4())
        db.add(Campaign(id=cid, topic="t", audience_goal="REVENUE", platforms=["x"],
                        status="SUCCESS", workspace_id=workspace_a["workspace_id"],
                        brand_id=workspace_a["brand_id"], channel_id=ch))
        db.add(RevenueEntry(campaign_id=cid, source="PLATFORM_API", amount=100000.0,
                            is_estimate=False, channel_id=ch))
        db.add(RevenueEntry(campaign_id=cid, source="ESTIMATE", amount=999999.0,
                            is_estimate=True, channel_id=ch))
        db.add(CostLog(campaign_id=cid, agent_name="x", kind="RENDER", provider="ffmpeg",
                       amount_usd=70000.0, channel_id=ch))
    with session_scope() as db:
        pc = M.profit_center(db, channel_id=ch)
    assert pc["revenue_actual_usd"] == 100000.0
    assert pc["revenue_estimated_usd"] == 999999.0        # kept separate
    assert pc["net_profit_usd"] == 30000.0               # actual - cost, NOT incl. estimate
    assert pc["profit_margin"] == 0.3


def test_monetization_agent_recommends_a_model(workspace_a):
    with session_scope() as db:
        ch = db.get(Channel, workspace_a["channel1_id"])
        out = M.monetization_agent(db, ch)
    assert out["recommended_primary_model"] in M.REVENUE_MODELS
    assert set(out["model_fit"]) <= set(M.REVENUE_MODELS) and len(out["model_fit"]) >= 5
    assert any("separately" in n for n in out["notes"])


def test_sponsor_guard_blocks_forbidden_claim_and_bad_superlative():
    deal = {"sponsor": "AcmeCorp", "forbidden_claims": ["경쟁사 언급"],
            "required_mentions": ["업계 유일의 100% 무결점 제품"], "deliverables": {}}
    res = M.sponsor_content_guard(
        sponsor_deal=deal,
        script_text="이 제품은 정말 좋습니다. 경쟁사 언급도 살짝 했습니다.",
        verified_fact_texts=["제품 A는 2년 보증을 제공한다"],
        brand_risk_policy={"blocked_sponsor_categories": []},
    )
    assert res["verdict"] == "BLOCK"
    assert any("forbidden_claim" in f for f in res["findings"])
    assert any("superlative" in f for f in res["findings"])


def test_sponsor_guard_blocks_blocked_category():
    res = M.sponsor_content_guard(
        sponsor_deal={"sponsor": "LuckyBet 카지노", "deliverables": {"type": "카지노 프로모션"}},
        script_text="오늘의 스폰서를 소개합니다.",
        verified_fact_texts=[],
        brand_risk_policy={"blocked_sponsor_categories": ["카지노", "도박"]},
    )
    assert res["verdict"] == "BLOCK"


def test_sponsor_guard_ok_when_clean():
    res = M.sponsor_content_guard(
        sponsor_deal={"sponsor": "GoodTool", "forbidden_claims": [], "required_mentions": ["GoodTool을 사용합니다"]},
        script_text="오늘은 GoodTool을 사용합니다. 유용한 기능을 소개할게요.",
        verified_fact_texts=["GoodTool은 무료 플랜을 제공한다"],
        brand_risk_policy={},
    )
    assert res["verdict"] == "OK"


def test_affiliate_disclosure_is_added_not_removed():
    r_missing = M.enforce_affiliate_disclosure(
        "이 카메라 정말 좋아요. 링크는 아래에.", has_affiliate_link=True,
        default_disclosure="본 영상은 제휴 링크를 포함합니다.")
    assert r_missing["status"] == "ADDED"
    assert "제휴" in r_missing["script"]

    r_present = M.enforce_affiliate_disclosure(
        "유료 광고 포함. 이 카메라 좋아요.", has_affiliate_link=True,
        default_disclosure="본 영상은 제휴 링크를 포함합니다.")
    assert r_present["status"] == "PRESENT"
    assert r_present["script"] == "유료 광고 포함. 이 카메라 좋아요."

    r_na = M.enforce_affiliate_disclosure("일반 콘텐츠", has_affiliate_link=False,
                                          default_disclosure="x")
    assert r_na["status"] == "N/A"


def test_commercial_guards_flag_fake_tactics_and_density():
    recent = [{"is_sponsored": True}, {"is_sponsored": True}, {"has_affiliate": True},
              {"is_sponsored": False}]
    g = M.commercial_guards(recent_contents=recent,
                            script_text="딱 오늘만 마감 임박! 모두가 샀어요.")
    assert g["verdict"] == "BLOCK"                      # fake scarcity + fake social proof
    assert g["sponsored_density"] == 0.5
    assert any("fake_scarcity" in t for t in g["fake_tactics"])

    clean = M.commercial_guards(
        recent_contents=[{"is_sponsored": False}] * 5,
        script_text="오늘은 카메라 기능을 차분히 설명합니다.")
    assert clean["verdict"] == "OK"
