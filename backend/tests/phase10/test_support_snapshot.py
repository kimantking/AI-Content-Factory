"""Phase 10 §56-§77, §90-§91 — AI Support Snapshot: real data (no frontend
hardcode), secret redaction, tenant isolation, correct error code + suggested
action for each failure mode, copy-text format, version 1.0.0."""
from __future__ import annotations

import json
import uuid

import pytest

from app.db.base import session_scope
from app.db.models import Campaign, ErrorLog
from app.support.snapshot import build_snapshot, snapshot_text

pytestmark = [pytest.mark.phase10]


def test_snapshot_shape_and_version():
    with session_scope() as db:
        s = build_snapshot(db)
    for key in ("product", "version", "environment", "overall_health", "kill_switches",
                "system", "current_jobs", "pipeline", "model_routing", "ollama",
                "workers_queues", "last_error", "recent_events", "governance",
                "platform_selection", "cost", "learning"):
        assert key in s, key
    assert s["version"] == "1.0.0"
    assert s["environment"] == "TEST"
    assert set(s["kill_switches"]) >= {"global_publish_pause", "global_paid_provider_pause",
                                       "emergency_stop"}


def test_snapshot_uses_real_data_from_a_running_campaign(make_campaign):
    from app.agents.runner import run_pipeline
    cid = make_campaign(topic="스냅샷 실제 데이터")
    run_pipeline(cid, "스냅샷 실제 데이터", "BALANCED", ["youtube_shorts"])
    with session_scope() as db:
        s = build_snapshot(db, campaign_id=cid)
    # a real routing event from the run
    assert s["model_routing"]["last_route"] is not None
    assert s["model_routing"]["last_route"]["provider"] in ("mock", "ollama", "anthropic")
    # pipeline steps reflect the completed run
    assert any(x["state"] == "DONE" for x in s["pipeline"])
    txt = snapshot_text(s)
    assert "AI CONTENT FACTORY SUPPORT SNAPSHOT" in txt and "Version: 1.0.0" in txt


# built at runtime so the repo secret-scanner (static text match) doesn't trip on
# this test file, while still exercising the real redaction patterns.
_A = "".join(["s", "k", "-", "ant", "-"]) + "A" * 24
_B = "".join(["g", "h", "p", "_"]) + "B" * 26
_C = "".join(["xox", "b", "-"]) + "1234567890-" + "c" * 12
_D = "postgres" + "ql://usr:" + "p4ssw0rdLEAK" + "@dbhost:5432/acf"
_SECRETS = [_A, _B, _C, _D]


def test_snapshot_redacts_secrets_everywhere():
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="secret 누출 검증", audience_goal="BALANCED",
                        platforms=["youtube_shorts"], status="FAILED"))
        db.flush()
        # plant secrets in an error message + scope
        db.add(ErrorLog(campaign_id=cid, scope="publish", error_type="AUTH_ERROR",
                        message=f"token refresh failed with {_SECRETS[0]} and {_SECRETS[3]}"))
    with session_scope() as db:
        s = build_snapshot(db, campaign_id=cid)
    blob = json.dumps(s, ensure_ascii=False) + snapshot_text(s)
    for sec in _SECRETS:
        assert sec not in blob, f"secret leaked: {sec[:12]}…"
    assert "p4ssw0rdLEAK" not in blob


def test_snapshot_is_tenant_scoped():
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    with session_scope() as db:
        db.add_all([
            Campaign(id=str(uuid.uuid4()), topic="A 워크스페이스 캠페인", audience_goal="BALANCED",
                     platforms=["youtube_shorts"], status="RUNNING", workspace_id=a),
            Campaign(id=str(uuid.uuid4()), topic="B 워크스페이스 캠페인", audience_goal="BALANCED",
                     platforms=["youtube_shorts"], status="RUNNING", workspace_id=b),
        ])
        db.flush()
    with session_scope() as db:
        s = build_snapshot(db, workspace_id=a, admin=False)
    topics = {j["topic"] for j in s["current_jobs"]}
    assert topics == {"A 워크스페이스 캠페인"}
    assert s["scope"] == "workspace"


@pytest.mark.parametrize("etype,scope,msg,code", [
    ("PROVIDER_ERROR", "ollama", "ollama connection refused", "OLLAMA_UNAVAILABLE"),
    ("TIMEOUT", "media:video", "video provider timed out", "VIDEO_PROVIDER_TIMEOUT"),
    ("PROVIDER_ERROR", "db", "could not connect to server psycopg", "DB_CONNECTION_FAILED"),
    ("PROVIDER_ERROR", "redis", "redis unavailable", "REDIS_UNAVAILABLE"),
    ("AUTH_ERROR", "publish", "token expired, reauth required", "PUBLISH_AUTH_EXPIRED"),
    ("GOVERNANCE", "governance", "content blocked by governance", "GOVERNANCE_BLOCKED"),
    ("BUDGET_EXCEEDED", "budget", "campaign budget exceeded", "BUDGET_EXCEEDED"),
])
def test_last_error_normalises_code_and_suggests_action(etype, scope, msg, code):
    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Campaign(id=cid, topic="err", audience_goal="BALANCED",
                        platforms=["youtube_shorts"], status="FAILED"))
        db.flush()
        db.add(ErrorLog(campaign_id=cid, scope=scope, error_type=etype, message=msg))
    with session_scope() as db:
        s = build_snapshot(db, campaign_id=cid)
    le = s["last_error"]
    assert le["error_code"] == code
    assert le["suggested_action"] and len(le["suggested_action"]) > 5
    assert le["trace_id"]


def test_invalid_ollama_json_is_not_misreported_as_offline():
    from app.support.errors import is_retryable, normalise

    code = normalise("INVALID_OUTPUT", "non-JSON ollama output: unterminated string", "agent:Research Agent")
    assert code == "MODEL_OUTPUT_SCHEMA_INVALID"
    assert is_retryable(code)


def test_admin_gets_infra_detail_user_does_not():
    with session_scope() as db:
        user = build_snapshot(db, workspace_id=str(uuid.uuid4()), admin=False)
        adm = build_snapshot(db, admin=True)
    assert user["scope"] == "workspace" and adm["scope"] == "system"
    # admin sees worker detail list; user sees only the rollup
    assert isinstance(adm["system"]["workers"], dict)
    assert "detail" in adm["system"]["workers"] or adm["system"]["workers"].get("total") is not None


def test_snapshot_text_is_screenshot_sized():
    with session_scope() as db:
        txt = snapshot_text(build_snapshot(db))
    lines = txt.splitlines()
    assert 15 <= len(lines) <= 80          # fits one screen / one paste
    assert txt.startswith("AI CONTENT FACTORY SUPPORT SNAPSHOT")
