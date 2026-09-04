from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.db.base import session_scope
from app.db.models import Campaign, CostLog, PerformanceScore, PlatformContent, RevenueEntry
from app.db.models_mb import Channel
from app.mb import channel_manager as CM
from app.mb import portfolio as PF
from app.mb import routing as RT


def _seed_channel_data(ws, brand, channel, *, n=14, score=70.0, cost_each=1.0, rev_each=5.0):
    with session_scope() as db:
        for i in range(n):
            cid = str(uuid.uuid4())
            db.add(Campaign(id=cid, topic=f"주제 {i % 4}", audience_goal="VIEWS",
                            platforms=["youtube_shorts"], status="SUCCESS",
                            workspace_id=ws, brand_id=brand, channel_id=channel,
                            created_at=datetime.now(timezone.utc) - timedelta(days=i)))
            pcid = str(uuid.uuid4())
            db.add(PlatformContent(id=pcid, campaign_id=cid, platform="youtube_shorts",
                                   content_type="SHORT_VIDEO"))
            db.add(PerformanceScore(publication_id=str(uuid.uuid4()), campaign_id=cid,
                                    content_id=pcid, platform="youtube_shorts",
                                    content_type="SHORT_VIDEO", objective="VIEWS",
                                    score=min(100.0, score + (20 if i == 0 else 0)),  # one outlier
                                    is_outlier=(i == 0), has_anomaly=False))
            db.add(CostLog(campaign_id=cid, agent_name="x", kind="RENDER", provider="ffmpeg",
                           amount_usd=cost_each, channel_id=channel))
            db.add(RevenueEntry(campaign_id=cid, source="PLATFORM_API", amount=rev_each,
                                is_estimate=False, channel_id=channel,
                                occurred_at=datetime.now(timezone.utc) - timedelta(days=i)))


# ---- Channel Manager --------------------------------------------------- #

def test_channel_health_and_scale_status(workspace_a):
    _seed_channel_data(workspace_a["workspace_id"], workspace_a["brand_id"],
                       workspace_a["channel1_id"], n=14, score=72.0)
    with session_scope() as db:
        ch = db.get(Channel, workspace_a["channel1_id"])
        snap = CM.health_score(db, ch)
        assert 0 <= snap.score <= 100
        assert snap.sample_size == 14
        assert snap.scale_status in ("SCALE", "SCALE_CAUTIOUSLY", "HOLD")


def test_warmup_channel_never_confident_scale(workspace_a):
    # channel2 is WARMUP with no data
    with session_scope() as db:
        ch = db.get(Channel, workspace_a["channel2_id"])
        snap = CM.health_score(db, ch)
        assert snap.scale_status == "NOT_ENOUGH_DATA"
        plan = CM.operating_plan(db, ch, snap)
        assert plan.plan["warmup"] is True
        assert plan.plan["content_mix"]["EXPERIMENT"] >= 0.2
        assert "accumulate_data" in plan.plan["recommended_actions"]


def test_single_outlier_does_not_trigger_scale(workspace_a):
    # 8 mediocre campaigns + 1 viral outlier (excluded) -> median is low -> not SCALE
    _seed_channel_data(workspace_a["workspace_id"], workspace_a["brand_id"],
                       workspace_a["channel1_id"], n=9, score=42.0)
    with session_scope() as db:
        ch = db.get(Channel, workspace_a["channel1_id"])
        snap = CM.health_score(db, ch)
        assert snap.scale_status in ("TEST_MORE", "HOLD", "REVIEW", "SCALE_CAUTIOUSLY")
        assert snap.scale_status != "SCALE"


# ---- Portfolio Manager ------------------------------------------------ #

def test_portfolio_objective_changes_budget_allocation(workspace_a):
    ws = workspace_a["workspace_id"]
    _seed_channel_data(ws, workspace_a["brand_id"], workspace_a["channel1_id"], n=16, score=78.0,
                       cost_each=0.5, rev_each=1.0)     # high performance, low revenue
    _seed_channel_data(ws, workspace_a["brand_id"], workspace_a["channel2_id"], n=16, score=45.0,
                       cost_each=0.5, rev_each=12.0)    # low performance, high revenue
    with session_scope() as db:
        db.get(Channel, workspace_a["channel2_id"]).lifecycle = "ACTIVE"
        growth = PF.allocate_budget(db, ws, objective="GROWTH", total_usd=100.0)
    with session_scope() as db:
        revenue = PF.allocate_budget(db, ws, objective="REVENUE", total_usd=100.0)

    c1, c2 = workspace_a["channel1_id"], workspace_a["channel2_id"]
    # GROWTH should favour the high-performance channel; REVENUE the high-revenue one
    assert growth["allocations"][c1] > revenue["allocations"][c1]
    assert revenue["allocations"][c2] > growth["allocations"][c2]


def test_portfolio_budget_is_hard_capped(workspace_a):
    with session_scope() as db:
        alloc = PF.allocate_budget(db, workspace_a["workspace_id"], total_usd=10_000.0)
    # workspace hard daily budget is 100
    assert alloc["total_usd"] <= 100.0 + 1e-6
    assert alloc["hard_capped"] is True
    assert sum(alloc["allocations"].values()) <= alloc["total_usd"] + 1.0


def test_portfolio_recommendations_never_auto_delete(workspace_a):
    _seed_channel_data(workspace_a["workspace_id"], workspace_a["brand_id"],
                       workspace_a["channel1_id"], n=16, score=25.0)  # sustained underperformance
    with session_scope() as db:
        recs = PF.recommendations(db, workspace_a["workspace_id"])
        rows = [(r.action, r.confidence, r.sample_size) for r in recs]
    actions = {a for a, _, _ in rows}
    assert "DELETE" not in actions and "ARCHIVE" not in actions
    assert actions & {"REPOSITION_RECOMMENDED", "REDUCE_PRODUCTION", "EXPERIMENT", "KEEP"}
    assert all(c <= 1.0 and n >= 0 for _, c, n in rows)


def test_min_exploration_floor_keeps_every_channel_funded(workspace_a):
    ws = workspace_a["workspace_id"]
    _seed_channel_data(ws, workspace_a["brand_id"], workspace_a["channel1_id"], n=20, score=90.0)
    with session_scope() as db:
        db.get(Channel, workspace_a["channel2_id"]).lifecycle = "ACTIVE"
        alloc = PF.allocate_budget(db, ws, total_usd=100.0, min_exploration_frac=0.05)
    assert alloc["allocations"][workspace_a["channel2_id"]] >= alloc["min_exploration_floor_usd"] - 0.01


# ---- Routing + cannibalization ------------------------------------- #

def test_routing_respects_brand_policy_block(workspace_a):
    with session_scope() as db:
        d = RT.route(db, workspace_id=workspace_a["workspace_id"], topic="온라인 도박 사이트 추천")
        # brand blocks "도박" -> no channel should be routed
        assert d.routed_channel_id is None
        assert all(s["total"] == 0.0 for s in d.scores.values())


def test_routing_picks_a_channel_for_ok_topic(workspace_a):
    with session_scope() as db:
        d = RT.route(db, workspace_id=workspace_a["workspace_id"], topic="AI로 바뀌는 직업 전망")
        assert d.routed_channel_id in (workspace_a["channel1_id"], workspace_a["channel2_id"])


def test_strict_channel_topics_route_once_per_matching_platform(workspace_a):
    with session_scope() as db:
        for channel_id in (workspace_a["channel1_id"], workspace_a["channel2_id"]):
            db.get(Channel, channel_id).content_strategy = {
                "concept": "직장인을 위한 AI 자동화",
                "topics": ["AI 도구", "업무 자동화"],
                "blocked_topics": [],
                "strict_topic_match": True,
            }
    with session_scope() as db:
        d = RT.route(db, workspace_id=workspace_a["workspace_id"], topic="직장인을 위한 AI 도구 사용법")
        routed = d.decision["routed_channels"]
        assert routed["youtube_shorts"] == workspace_a["channel1_id"]
        assert routed["tiktok"] == workspace_a["channel2_id"]


def test_strict_channel_topics_block_unrelated_upload(workspace_a):
    with session_scope() as db:
        for channel_id in (workspace_a["channel1_id"], workspace_a["channel2_id"]):
            db.get(Channel, channel_id).content_strategy = {
                "concept": "AI 자동화 전문 채널",
                "topics": ["AI 도구"],
                "blocked_topics": ["도박"],
                "strict_topic_match": True,
            }
    with session_scope() as db:
        d = RT.route(db, workspace_id=workspace_a["workspace_id"], topic="제주도 감귤 농장 여행기")
        assert d.routed_channel_id is None
        assert d.decision["routed_channels"] == {}
        assert all(score["eligible"] is False for score in d.scores.values())


def test_cannibalization_detected_for_near_identical_topics(workspace_a):
    ws = workspace_a["workspace_id"]
    with session_scope() as db:
        for cid in (workspace_a["channel1_id"], workspace_a["channel2_id"]):
            db.add(Campaign(id=str(uuid.uuid4()), topic="AI가 대체할 직업 순위 총정리",
                            audience_goal="VIEWS", platforms=["x"], status="RUNNING",
                            workspace_id=ws, brand_id=workspace_a["brand_id"], channel_id=cid,
                            created_at=datetime.now(timezone.utc)))
    with session_scope() as db:
        st = RT.cannibalization_status(db, ws, "AI가 대체할 직업 순위 총정리", angle="순위 총정리")
        assert st["status"] in ("OVERLAP", "CANNIBALIZATION_RISK")
        assert st["matches"]
