from app.db.base import session_scope
from app.db.models import Campaign
from app.tasks import _enqueue_media_after_text


def _campaign(mode: str, *, step: str = "done", status: str = "SUCCESS") -> str:
    with session_scope() as session:
        camp = Campaign(
            topic="자동 영상 테스트",
            audience_goal="BALANCED",
            platforms=["youtube_shorts"],
            status=status,
            current_step=step,
            execution_mode=mode,
        )
        session.add(camp)
        session.flush()
        return camp.id


def test_completed_production_automatically_enters_media_queue(monkeypatch):
    campaign_id = _campaign("CREATE_ONLY")
    calls = []
    monkeypatch.setattr("app.tasks.run_media_task.apply", lambda **kwargs: calls.append(kwargs))

    assert _enqueue_media_after_text(campaign_id, None) is True
    assert calls == [{"args": [campaign_id, ["youtube_shorts"]]}]
    with session_scope() as session:
        camp = session.get(Campaign, campaign_id)
        assert camp.status == "RUNNING"
        assert camp.current_step == "media:queued"


def test_media_handoff_is_idempotent(monkeypatch):
    campaign_id = _campaign("CREATE_AND_LEARN")
    calls = []
    monkeypatch.setattr("app.tasks.run_media_task.apply", lambda **kwargs: calls.append(kwargs))

    assert _enqueue_media_after_text(campaign_id, None) is True
    assert _enqueue_media_after_text(campaign_id, None) is False
    assert len(calls) == 1


def test_learning_mode_never_starts_media(monkeypatch):
    campaign_id = _campaign("LEARN_ONLY")
    monkeypatch.setattr(
        "app.tasks.run_media_task.apply",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("media must not start")),
    )

    assert _enqueue_media_after_text(campaign_id, None) is False


def test_media_loader_accepts_automatic_queue_handoff():
    from app.agents.media_nodes import _phase1_ready

    queued = Campaign(status="RUNNING", current_step="media:queued")
    resumed = Campaign(status="RUNNING", current_step="media:images")
    incomplete = Campaign(status="RUNNING", current_step="qa_script")

    assert _phase1_ready(queued) is True
    assert _phase1_ready(resumed) is True
    assert _phase1_ready(incomplete) is False


def test_korean_output_guard_rejects_english_only_content():
    import pytest

    from app.agents.media_nodes import _require_korean
    from app.providers.errors import ProviderError

    _require_korean({"script": "한국어 대본입니다."}, ("script",), task="test")
    with pytest.raises(ProviderError):
        _require_korean({"script": "English only."}, ("script",), task="test")


def test_platform_adapt_uses_korean_master_copy_when_local_model_returns_english():
    from app.agents.media_nodes import _korean_platform_fallback, _require_korean

    result = _korean_platform_fallback(
        {"hook": "English hook", "script": "English script", "title": "English title",
         "caption": "English caption", "cta": "Follow me"},
        {"topic": "요즘 핫한 이야기", "master_hook": "지금 가장 중요한 이야기",
         "master_script": "오늘의 핵심 내용을 한국어로 설명합니다."},
    )

    _require_korean(result, ("hook", "script", "title", "caption"), task="test")
    assert result["script"] == "오늘의 핵심 내용을 한국어로 설명합니다."
    assert result["cta"] == "다음 이야기도 확인해 보세요."


def test_platform_adapt_builds_korean_script_when_master_copy_is_also_english():
    from app.agents.media_nodes import _korean_platform_fallback, _require_korean

    result = _korean_platform_fallback(
        {"hook": "English hook", "script": "English script", "title": "English title",
         "caption": "English caption"},
        {"topic": "요즘 핫한 이야기", "master_hook": "English hook",
         "master_script": "English master script", "usable_fact_texts": []},
    )

    _require_korean(result, ("hook", "script", "title", "caption"), task="test")
    assert "요즘 핫한 이야기" in result["script"]
