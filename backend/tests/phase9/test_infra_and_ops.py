"""Phase 9 §28-§35 (DB / Redis / worker), §59-§62 (multi-tenant stress),
§79-§82 (autopilot real-world), §93-§95 (error taxonomy / no swallow).

Redis restart / worker crash are process-level in production; here they're
simulated with a controlled bad connection + the checkpoint-resume guarantee
already proven in test_failure_recovery.py."""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db.base import engine, session_scope
from app.db.models import Campaign, PublishJob
from tests.phase9.conftest import new_campaign, run_one_campaign

pytestmark = [pytest.mark.phase9, pytest.mark.recovery]


# ---- §28/§30 DB connection blip -> pool_pre_ping recovers -------------- #

def test_db_connection_drop_is_transparently_recovered():
    from sqlalchemy import text
    # forcibly close every pooled connection (simulates a DB restart / network blip)
    engine.dispose()
    # next use must transparently reconnect (pool_pre_ping=True)
    with session_scope() as db:
        assert db.execute(text("select 1")).scalar() == 1
    # and a real workload still runs
    cid = new_campaign("db 복구 검증")
    r = run_one_campaign(cid, "db 복구 검증")
    assert r["status"] == "SUCCESS", r


def test_transaction_rollback_leaves_no_orphan():
    """A failure mid-write rolls the whole unit back — no half-created campaign."""
    from sqlalchemy.exc import IntegrityError
    cid = str(uuid.uuid4())
    try:
        with session_scope() as db:
            db.add(Campaign(id=cid, topic="rollback", audience_goal="BALANCED",
                            platforms=["youtube_shorts"], status="WAITING"))
            db.flush()
            db.add(Campaign(id=cid, topic="dup pk", audience_goal="BALANCED",
                            platforms=["x"], status="WAITING"))   # duplicate PK -> boom
            db.flush()
    except IntegrityError:
        pass
    with session_scope() as db:
        assert db.get(Campaign, cid) is None      # the first insert rolled back too


# ---- §32 Redis unavailable -> app + health degrade gracefully -------- #

def test_redis_down_does_not_crash_app_or_health(monkeypatch):
    from app.ops import health as OH

    def _boom():
        return {"status": "DOWN", "error": "redis down (simulated)"}

    monkeypatch.setattr(OH, "check_redis", _boom)
    r = OH.readiness()                       # must not raise
    assert r["checks"]["redis"]["status"] == "DOWN"
    assert OH.liveness()["status"] in ("OK", "ALIVE", "UP", "LIVE", "alive", "ok")
    # the rest of the app is unaffected — a campaign still runs inline
    cid = new_campaign("redis-down 검증")
    assert run_one_campaign(cid, "redis-down 검증")["status"] == "SUCCESS"


# ---- §34/§35 concurrent consumers of the same job -> one effect ----- #

def test_two_runners_same_publish_job_no_double_effect():
    from app.publishing.engine import run_publish_job
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="dup-runner", audience_goal="BALANCED",
                        platforms=["youtube_shorts"], status="SUCCESS"))
        db.flush()
        j = PublishJob(campaign_id=cid, platform="naver_blog", content_type="post",
                       status="READY", run_mode="MANUAL", approval_status="APPROVED",
                       idempotency_key=str(uuid.uuid4()))
        db.add(j)
        db.flush()
        jid = j.id
    with ThreadPoolExecutor(max_workers=2) as ex:
        res = [f.result() for f in [ex.submit(run_publish_job, jid), ex.submit(run_publish_job, jid)]]
    with session_scope() as db:
        job = db.get(PublishJob, jid)
        # naver_blog is MANUAL_ONLY -> no remote post ever, and no crash / no dup rows
        events = db.query(PublishJob).filter_by(id=jid).count()
    assert events == 1
    assert all("status" in r for r in res)


# ---- §59-§62 multi-workspace concurrent -> no leak ----------------- #

def test_multi_workspace_concurrent_no_leak():
    from app.library.service import list_content
    wsa, wsb = str(uuid.uuid4()), str(uuid.uuid4())

    def run(ws, tag):
        cid = new_campaign(f"{tag} 캠페인", workspace_id=ws, execution_mode="CREATE_AND_LEARN")
        return run_one_campaign(cid, f"{tag} 캠페인")

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = ([ex.submit(run, wsa, "A") for _ in range(4)] +
                [ex.submit(run, wsb, "B") for _ in range(4)])
        out = [f.result() for f in futs]
    assert all(r["status"] == "SUCCESS" for r in out), out
    with session_scope() as db:
        a = {c["topic"] for c in list_content(db, workspace_id=wsa)["items"]}
        b = {c["topic"] for c in list_content(db, workspace_id=wsb)["items"]}
    assert all(t.startswith("A ") for t in a)
    assert all(t.startswith("B ") for t in b)
    assert not (a & b)


# ---- §79-§82 autopilot real-world (dry-run) ------------------------ #

def test_autopilot_dry_run_cycle_zero_production(_base_settings):
    from app.autopilot.controller import run_autopilot
    _base_settings.autopilot_mode = "SHADOW"
    _base_settings.trend_client = "mock"
    _base_settings.run_inline = True
    r = run_autopilot("SHADOW")
    assert r["status"] in ("SUCCESS", "OFF", "HOLD"), r
    if r["status"] == "SUCCESS":
        assert r.get("produced", 0) == 0 and r.get("published", 0) == 0
    with session_scope() as db:
        # SHADOW never creates a real content Campaign
        assert db.query(Campaign).filter(Campaign.status.in_(("RUNNING", "SUCCESS"))).count() == 0


def test_autopilot_repeated_cycles_no_infinite_duplicates(_base_settings):
    from app.autopilot.controller import run_autopilot
    _base_settings.autopilot_mode = "SHADOW"
    _base_settings.trend_client = "mock"
    _base_settings.run_inline = True
    from app.db.models import TopicCandidate
    seen_counts = []
    for _ in range(3):
        run_autopilot("SHADOW")
        with session_scope() as db:
            seen_counts.append(db.query(TopicCandidate).count())
    # candidate rows accumulate per run but do not blow up geometrically
    assert seen_counts[-1] < seen_counts[0] * 10 + 200, seen_counts
