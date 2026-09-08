from app.db.base import session_scope
from app.db.models_learn import LearningJob, ReferenceSource
from app.intel.engine import add_urls, run_learning_job


def test_failed_fetch_is_not_completed_learning(tenant):
    with session_scope() as db:
        job = add_urls(db, urls=["https://example.com/not-registered"],
                       workspace_id=tenant["workspace_id"])
        result = run_learning_job(db, job.id)
        assert result["ok"] is False
        assert db.get(LearningJob, job.id).status == "FAILED"
        assert result["counters"]["fetch_failed"] == 1


def test_mixed_result_is_partial(tenant):
    with session_scope() as db:
        job = add_urls(db, urls=["https://example.com/mt-report", "https://example.com/not-registered"],
                       workspace_id=tenant["workspace_id"])
        result = run_learning_job(db, job.id)
        assert result["status"] == "PARTIAL"
        assert result["counters"]["ready"] == 1
        assert result["counters"]["fetch_failed"] == 1


def test_video_page_does_not_claim_visual_learning(tenant, monkeypatch):
    from app.intel import engine
    from app.intel.fetch import FetchResult

    monkeypatch.setattr(engine, "fetch", lambda url: FetchResult(
        ok=True, status=200, final_url=url, content_type="text/html", body=b"<html>Video</html>"))
    with session_scope() as db:
        job = add_urls(db, urls=["https://www.youtube.com/watch?v=abcdefghijk"],
                       workspace_id=tenant["workspace_id"])
        result = run_learning_job(db, job.id)
        source = db.query(ReferenceSource).filter_by(learning_job_id=job.id).one()
        assert result["ok"] is False
        assert source.status == "BLOCKED"
        assert "아직 지원되지" in source.error
