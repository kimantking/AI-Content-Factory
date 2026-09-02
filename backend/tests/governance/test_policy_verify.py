"""AUDIT-P7-001 — human-in-the-loop platform-policy verification.

No live policy fetch: the module produces a review queue and records a named
reviewer's attestation, preserving LEGAL_REVIEW_REQUIRED labelling.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db.base import session_scope
from app.db.models_gov import GovernanceEvent, PolicyRegistry
from app.governance.policy import seed_policy_registry
from app.governance.policy_verify import record_verification, verification_report
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_stale_platform_shows_in_review_queue(_base_settings):
    _base_settings.policy_max_age_days = 30
    with session_scope() as db:
        seed_policy_registry(db, force=True)
        old = datetime.now(timezone.utc) - timedelta(days=90)
        for r in db.query(PolicyRegistry).filter_by(platform="tiktok"):
            r.last_verified_at = old
        db.flush()
        rep = verification_report(db)
    tt = next(i for i in rep["all"] if i["platform"] == "tiktok")
    assert tt["stale"] is True and tt["needs_review"] is True
    assert tt["review_label"] == "LEGAL_REVIEW_REQUIRED"
    assert "tiktok" in [q["platform"] for q in rep["queue"]]


def test_unknown_rule_flags_review_even_if_fresh(_base_settings):
    _base_settings.policy_max_age_days = 3650
    with session_scope() as db:
        seed_policy_registry(db, force=True)
        r = db.query(PolicyRegistry).filter_by(platform="x").first()
        r.status = "UNKNOWN"
        db.flush()
        rep = verification_report(db, platform="x")
    xi = rep["all"][0]
    assert xi["unknown_rules"] and xi["needs_review"] is True


def test_record_verification_bumps_timestamp_and_audits(_base_settings):
    _base_settings.policy_max_age_days = 30
    with session_scope() as db:
        seed_policy_registry(db, force=True)
        for r in db.query(PolicyRegistry).filter_by(platform="tiktok"):
            r.last_verified_at = datetime.now(timezone.utc) - timedelta(days=90)
        db.flush()
        res = record_verification(db, platform="tiktok", actor="reviewer@acme.test",
                                  outcome="CONFIRMED_CURRENT", note="checked TikTok help centre")
        assert res["rules_touched"] >= 1
        rep = verification_report(db, platform="tiktok")
        ev = db.query(GovernanceEvent).filter_by(kind="POLICY_VERIFIED").all()
        actors = [e.actor for e in ev]
    assert rep["all"][0]["stale"] is False
    assert "reviewer@acme.test" in actors


def test_unknown_stays_unknown_without_explicit_activation(_base_settings):
    with session_scope() as db:
        seed_policy_registry(db, force=True)
        r = db.query(PolicyRegistry).filter_by(platform="x").first()
        r.status = "UNKNOWN"
        rid = r.rule_id
        db.flush()
        # default call: does NOT activate
        record_verification(db, platform="x", actor="rev", outcome="CONFIRMED_CURRENT")
        still = db.query(PolicyRegistry).filter_by(platform="x", rule_id=rid).one()
        assert still.status == "UNKNOWN"
        # explicit, attributed activation
        record_verification(db, platform="x", actor="rev", outcome="UPDATED",
                            rule_ids=[rid], activate_unknown=True)
        now_active = db.query(PolicyRegistry).filter_by(platform="x", rule_id=rid).one()
        assert now_active.status == "ACTIVE"


def test_record_verification_requires_named_reviewer(_base_settings):
    with session_scope() as db:
        seed_policy_registry(db, force=True)
        with pytest.raises(ValueError):
            record_verification(db, platform="tiktok", actor="  ")


def test_verification_endpoints(_base_settings):
    r = client.get("/api/policy/verification")
    assert r.status_code == 200
    assert "queue" in r.json() and "all" in r.json()
    p = client.post("/api/policy/verify",
                    json={"platform": "tiktok", "actor": "qa@acme.test",
                          "outcome": "CONFIRMED_CURRENT"})
    assert p.status_code == 200 and p.json()["rules_touched"] >= 1
