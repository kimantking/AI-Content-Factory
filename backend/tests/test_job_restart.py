from app.api.routes_campaigns import cancel_campaign, resume_campaign
from app.db.base import session_scope
from app.db.models import Campaign
from app.tasks import _mark_failed


def test_cancel_preserves_media_step_and_restart_routes_to_media(monkeypatch, make_campaign):
    cid = make_campaign()
    monkeypatch.setattr("app.api.routes_campaigns._revoke_campaign_tasks", lambda _: [])
    calls = []
    monkeypatch.setattr("app.tasks.run_media_task.apply", lambda **kw: calls.append(kw))
    with session_scope() as db:
        camp = db.get(Campaign, cid)
        camp.status, camp.current_step = "RUNNING", "media:voice"
    with session_scope() as db:
        assert cancel_campaign(cid, db)["status"] == "CANCELLED"
        assert db.get(Campaign, cid).current_step == "media:voice"
    _mark_failed(cid, RuntimeError("late worker failure"))
    with session_scope() as db:
        assert db.get(Campaign, cid).status == "CANCELLED"
        resume_campaign(cid, db)
    assert calls[0]["kwargs"] == {"resume": True}
    assert calls[0]["args"][0] == cid


def test_restart_queued_text_campaign(monkeypatch, make_campaign):
    cid = make_campaign()
    calls = []
    monkeypatch.setattr("app.tasks.run_campaign_task.apply", lambda **kw: calls.append(kw))
    with session_scope() as db:
        db.get(Campaign, cid).status = "CANCELLED"
    with session_scope() as db:
        assert resume_campaign(cid, db).status == "RUNNING"
    assert calls[0]["kwargs"] == {"resume": True}


def test_cancel_wins_over_worker_update_during_revoke(monkeypatch, make_campaign):
    cid = make_campaign()
    def racing_worker(_):
        with session_scope() as db:
            camp = db.get(Campaign, cid)
            camp.status, camp.current_step = "RUNNING", "research"
        return ["worker-task"]
    monkeypatch.setattr("app.api.routes_campaigns._revoke_campaign_tasks", racing_worker)
    with session_scope() as db:
        cancel_campaign(cid, db)
    with session_scope() as db:
        camp = db.get(Campaign, cid)
        assert camp.status == "CANCELLED"
        assert camp.current_step == "research"
