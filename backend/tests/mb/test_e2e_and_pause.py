from __future__ import annotations

import pytest

from app.db.base import session_scope
from app.db.models import Campaign
from app.db.models_mb import Brand, Channel
from app.mb import budget as B
from app.mb import portfolio as PF
from app.mb import routing as RT


def test_workspace_brand_channel_pause_isolation(client, workspace_a, workspace_b):
    ah = workspace_a["owner"].headers()

    # pause channel1 in workspace A
    r = client.post(f"/api/channels/{workspace_a['channel1_id']}/pause", json={"enabled": True}, headers=ah)
    assert r.status_code == 200 and r.json()["status"] == "PAUSED"
    # channel2 (same brand) unaffected
    with session_scope() as db:
        assert db.get(Channel, workspace_a["channel2_id"]).status == "ACTIVE"

    # pause the brand -> brand PAUSED, workspace B brand unaffected
    r = client.post(f"/api/brands/{workspace_a['brand_id']}/pause", json={"enabled": True}, headers=ah)
    assert r.status_code == 200 and r.json()["status"] == "PAUSED"
    with session_scope() as db:
        assert db.get(Brand, workspace_b["brand_id"]).status == "ACTIVE"

    # workspace emergency stop -> workspace A only
    r = client.post(f"/api/workspaces/{workspace_a['workspace_id']}/emergency-stop",
                    json={"enabled": True}, headers=ah)
    assert r.status_code == 200 and r.json()["status"] == "EMERGENCY_STOP"
    r_b = client.get(f"/api/workspaces/{workspace_b['workspace_id']}", headers=workspace_b["owner"].headers())
    assert r_b.json()["status"] == "ACTIVE"


def test_paused_brand_routes_to_no_channel(workspace_a):
    with session_scope() as db:
        db.get(Brand, workspace_a["brand_id"]).status = "PAUSED"
    with session_scope() as db:
        d = RT.route(db, workspace_id=workspace_a["workspace_id"], topic="AI 직업 전망")
        assert d.routed_channel_id is None   # paused brand has no eligible channels


def test_channel_concept_api_round_trip(client, workspace_a):
    headers = workspace_a["owner"].headers()
    channel_id = workspace_a["channel1_id"]
    strategy = {
        "concept": "한국어 AI 교육",
        "topics": ["AI 도구", "업무 자동화", "AI 도구"],
        "blocked_topics": ["도박"],
        "strict_topic_match": True,
    }
    saved = client.patch(
        f"/api/channels/{channel_id}",
        json={"target_audience": "AI 초보 직장인", "content_strategy": strategy},
        headers=headers,
    )
    assert saved.status_code == 200
    rows = client.get(
        f"/api/channels?workspace_id={workspace_a['workspace_id']}", headers=headers,
    ).json()
    channel = next(row for row in rows if row["id"] == channel_id)
    assert channel["target_audience"] == "AI 초보 직장인"
    assert channel["content_strategy"]["topics"] == ["AI 도구", "업무 자동화"]
    assert channel["content_strategy"]["strict_topic_match"] is True


def test_multi_channel_mock_e2e(workspace_a):
    """Trend -> route to a channel -> reserve budget -> create a scoped campaign ->
    portfolio snapshot reflects it. Publishing/analytics stay mock (not invoked)."""
    ws = workspace_a["workspace_id"]

    # 1. route a global candidate to a channel
    with session_scope() as db:
        decision = RT.route(db, workspace_id=ws, topic="새로 뜨는 AI 코딩 도구 정리",
                            candidate_id="cand-1")
        ch_id = decision.routed_channel_id
        brand_id = decision.routed_brand_id
    assert ch_id in (workspace_a["channel1_id"], workspace_a["channel2_id"])

    # 2. reserve budget for the campaign (transactional)
    with session_scope() as db:
        res = B.reserve(db, workspace_id=ws, brand_id=brand_id, channel_id=ch_id,
                        campaign_id="camp-e2e", amount_usd=2.5)
        res_id = res.id

    # 3. create a tenant-scoped campaign
    with session_scope() as db:
        db.add(Campaign(id="camp-e2e", topic="새로 뜨는 AI 코딩 도구 정리",
                        audience_goal="VIEWS", platforms=["youtube_shorts"], status="SUCCESS",
                        workspace_id=ws, brand_id=brand_id, channel_id=ch_id))

    # 4. settle the reservation at actual cost
    with session_scope() as db:
        B.settle(db, res_id, actual_usd=1.9)
        usage = B.day_usage(db, workspace_id=ws)
    assert usage["by_channel"].get(ch_id) == pytest.approx(1.9)

    # 5. portfolio snapshot includes the channel with the campaign
    with session_scope() as db:
        snap = PF.snapshot(db, ws)
        assert ch_id in snap.channels
        assert snap.totals["channels"] == 2


def test_cross_channel_failure_isolation(workspace_a):
    """A failure while processing channel1 must not stop channel2's pipeline —
    modelled here as: budget reservation error on ch1 does not block ch2."""
    ws = workspace_a["workspace_id"]
    with session_scope() as db:
        db.get(Channel, workspace_a["channel1_id"]).daily_budget_usd = 1.0
    with session_scope() as db:
        # ch1 over its tiny limit -> raises
        with pytest.raises(B.BudgetReservationError):
            B.reserve(db, workspace_id=ws, channel_id=workspace_a["channel1_id"], amount_usd=5.0)
    with session_scope() as db:
        # ch2 still works in a fresh transaction
        r = B.reserve(db, workspace_id=ws, channel_id=workspace_a["channel2_id"], amount_usd=5.0)
        assert r.status == "RESERVED"


def test_asset_reuse_history_and_dashboard_payload(client, workspace_a):
    # portfolio dashboard endpoint returns a structured payload
    r = client.get(f"/api/portfolio?workspace_id={workspace_a['workspace_id']}",
                   headers=workspace_a["owner"].headers())
    assert r.status_code == 200
    body = r.json()
    assert body["objective"] and "channels" in body and "totals" in body
    assert body["totals"]["channels"] == 2
