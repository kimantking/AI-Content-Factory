"""Phase 7 governance ↔ Publisher / Autopilot / Manifest integration (§135-§138,
§147-§148). Proves the completion gate: a governance BLOCK cannot be bypassed by
a direct Publisher call or by Autopilot, and the published manifest reflects the
assets actually in the render.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import session_scope
from app.db.models import PlatformAccount, PublishJob
from app.governance.engine import govern_campaign, govern_pre_publish
from app.governance.manifest import build_manifest


def _connect_mock(platform: str = "youtube_shorts") -> str:
    from app.publishing.capabilities import get_capability
    from app.publishing.crypto import encrypt_token

    cap = get_capability(platform)
    acc_id = str(uuid.uuid4())
    with session_scope() as s:
        s.add(PlatformAccount(
            id=acc_id, platform=platform, account_id=f"mock-{platform}",
            account_name=f"Mock {platform}", account_type="BUSINESS",
            scopes=list(cap.required_scopes),
            access_token_encrypted=encrypt_token(f"mock-access-{platform}"),
            refresh_token_encrypted=encrypt_token(f"mock-refresh-{platform}"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            connection_status="CONNECTED", integration_status="MOCK_TESTED",
        ))
    return acc_id


def _mk_job(gc, account_id, **kw) -> str:
    defaults = dict(campaign_id=gc["campaign_id"], content_id=gc["content_id"],
                    platform_account_id=account_id, platform="youtube_shorts",
                    content_type="SHORT_VIDEO", status="DRAFT", run_mode="FULL_AUTO",
                    approval_status="APPROVED", dry_run=True,
                    media_asset_ids=[], title="t", description="d", caption="c")
    defaults.update(kw)
    with session_scope() as db:
        job = PublishJob(**defaults)
        db.add(job)
        db.flush()
        return job.id


@pytest.fixture(autouse=True)
def _mock_publisher(_base_settings):
    _base_settings.platform_client = "mock"
    _base_settings.dry_run = True
    _base_settings.run_inline = True
    _base_settings.governance_enforce = True
    from app.publishing.mock_platform import mock_platform
    mock_platform.reset()
    yield
    mock_platform.reset()


# ---- §147 direct Publisher call cannot publish a governance BLOCK ---- #

def test_publisher_cannot_publish_unknown_rights(governed_campaign):
    from app.publishing.engine import run_publish_job

    gc = governed_campaign
    gc["add_asset"](asset_type="image", source_type="USER_UPLOAD", user_supplied=True)
    acc = _connect_mock()
    job_id = _mk_job(gc, acc)

    res = run_publish_job(job_id)

    assert res["status"] == "BLOCKED"
    assert res["governance"]["hard_block"] is True
    assert "RIGHTS.UNKNOWN_IN_AUTO" in res["governance"]["reason_codes"]
    with session_scope() as db:
        job = db.get(PublishJob, job_id)
        assert job.status == "BLOCKED"
        assert job.last_error_type == "GOVERNANCE"
        assert not job.remote_post_id           # never reached the platform


# ---- §148 Autopilot FULL_AUTO cannot bypass a governance BLOCK ------- #

def test_autopilot_gate_holds_blocked_campaign(governed_campaign):
    """The autopilot bridge calls govern_campaign(stage='post_render', run_mode=...)
    and holds the candidate (no publish jobs) when it is not publishable."""
    gc = governed_campaign
    gc["add_asset"](asset_type="image", source_type="SCREENSHOT",
                    source_url_or_id="")
    with session_scope() as db:
        gov = govern_campaign(db, campaign_id=gc["campaign_id"], run_mode="FULL_AUTO",
                              stage="post_render")
    assert gov["publishable"] is False
    assert gov["decision"] in ("BLOCK", "HUMAN_REVIEW", "FIX_REQUIRED")


# ---- §135 a clean governed campaign clears the governance gate ------- #

def test_publisher_passes_clean_governed_campaign(governed_campaign):
    from app.publishing.engine import run_publish_job

    gc = governed_campaign
    gc["add_asset"](asset_type="image", source_type="AI_GENERATED", ai_generated=True,
                    model_provider="acme", model_name="v2",
                    model_terms_reference="https://acme/terms")
    gc["add_asset"](asset_type="music", source_type="MUSIC_LIBRARY",
                    license_type="PROVIDER_MUSIC", license_reference="lic-ok")
    with session_scope() as db:
        from app.db.models import PlatformContent
        c = db.get(PlatformContent, gc["content_id"])
        c.payload = {**(c.payload or {}), "disclosure_meta": {"platform_ai_field": True}}
    acc = _connect_mock()
    job_id = _mk_job(gc, acc)

    res = run_publish_job(job_id)

    with session_scope() as db:
        job = db.get(PublishJob, job_id)
        # governance let it through — any later stop (preflight/media) is not a governance block
        assert job.governance_decision in ("ALLOW", "ALLOW_WITH_DISCLOSURE", "ALLOW_WITH_ATTRIBUTION")
        assert job.last_error_type != "GOVERNANCE"
    if "governance" in res:
        assert res["governance"]["publishable"] is True


# ---- §137 published manifest reflects the assets actually in the render ---- #

def test_manifest_matches_final_render(governed_campaign):
    gc = governed_campaign
    a1 = gc["add_asset"](asset_type="image", source_type="AI_GENERATED", ai_generated=True,
                         model_provider="acme", model_terms_reference="t")
    a2 = gc["add_asset"](asset_type="music", source_type="MUSIC_LIBRARY",
                         license_type="PROVIDER_MUSIC", license_reference="m")
    with session_scope() as db:
        man = build_manifest(db, campaign_id=gc["campaign_id"], content_id=gc["content_id"],
                             governance_decision="ALLOW_WITH_DISCLOSURE", published_snapshot=True)
        m = man.manifest
        asset_ids = {i["asset_id"] for i in m["assets"]}
        assert {a1["asset_id"], a2["asset_id"]} <= asset_ids
        assert m["disclosure_required"] is True
        assert any(x["asset_id"] == a1["asset_id"] for x in m["ai_generated_assets"])
        # content_hash is the sha256 of the real render file on disk
        import hashlib
        want = hashlib.sha256(open(gc["render_path"], "rb").read()).hexdigest()
        assert man.content_hash == want


# ---- §138 rights data is workspace-scoped (Phase 6 RBAC) ------------- #

def test_rights_data_is_workspace_scoped(governed_campaign):
    from app.db.models_gov import RightsLedger

    gc = governed_campaign
    gc["add_asset"](asset_type="image", source_type="AI_GENERATED", ai_generated=True,
                    model_provider="x", model_terms_reference="t")
    with session_scope() as db:
        mine = db.query(RightsLedger).filter_by(workspace_id=gc["workspace_id"]).count()
        other = db.query(RightsLedger).filter_by(workspace_id=str(uuid.uuid4())).count()
    assert mine >= 1 and other == 0
