from app.db.base import session_scope
from app.db.models import Campaign
from app.db.models_learn import ReferenceChunk, ReferenceSource
from app.intel.retrieval import retrieve_reference_context


def test_retrieval_filters_workspace_status_scope_and_topic():
    with session_scope() as db:
        campaign = Campaign(topic="한국어 영상", workspace_id="ours", platforms=[])
        db.add(campaign)
        db.flush()
        for marker, overrides in [
            ("usable", {}),
            ("foreign", {"workspace_id": "theirs"}),
            ("failed", {"status": "FETCH_FAILED"}),
            ("blocked", {"injection_flag": True}),
            ("private", {"scope": "THIS_CAMPAIGN", "campaign_id": "other"}),
        ]:
            attrs = dict(workspace_id="ours", scope="WORKSPACE", status="READY")
            attrs.update(overrides)
            source = ReferenceSource(url=f"https://example.com/{marker}", **attrs)
            db.add(source)
            db.flush()
            db.add(ReferenceChunk(reference_id=source.id, workspace_id=source.workspace_id,
                                  text=f"한국어 영상 근거 {marker}"))
        db.flush()
        result = retrieve_reference_context(db, campaign)
        assert "usable" in result
        for forbidden in ["foreign", "failed", "blocked", "private"]:
            assert forbidden not in result
        campaign.topic = "천문학"
        assert retrieve_reference_context(db, campaign) == ""


def test_prompt_persists_separately_and_reaches_gateway(monkeypatch):
    from app.agents import model_gateway as gateway

    captured = {}

    def capture(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("test stops before paid calls")

    monkeypatch.setattr(gateway, "run_routed", capture)
    monkeypatch.setattr(gateway, "_legacy_fallback", lambda *args, **kwargs: None)
    with session_scope() as db:
        campaign = Campaign(topic="한국어 영상", production_prompt="30초 웹툰 스타일", platforms=[])
        db.add(campaign)
        db.flush()
        db.expire(campaign)
        assert campaign.topic == "한국어 영상"
        assert campaign.production_prompt == "30초 웹툰 스타일"
        gateway.routed_complete(agent_name="Script Agent", task="script", system="한국어로 작성",
                                user="대본 작성", session=db, campaign_id=campaign.id)
        assert "30초 웹툰 스타일" in captured["user"]
