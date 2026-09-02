from __future__ import annotations

import pytest

from app.db.base import session_scope
from app.db.models import PlatformAccount
from app.publishing.base import PublishError
from app.publishing.token_manager import assert_credential_scope


# ---- workspace / brand / channel isolation (IDOR) ------------------- #

def test_cannot_read_another_workspaces_brand(client, workspace_a, workspace_b):
    a_headers = workspace_a["owner"].headers()
    # A's owner tries to read B's brand by id
    r = client.patch(f"/api/brands/{workspace_b['brand_id']}", json={"name": "hax"},
                     headers=a_headers)
    assert r.status_code == 403

    r2 = client.get(f"/api/channels/{workspace_b['channel_id']}/health", headers=a_headers)
    assert r2.status_code == 403

    r3 = client.get(f"/api/workspaces/{workspace_b['workspace_id']}", headers=a_headers)
    assert r3.status_code == 403


def test_channel_list_is_scoped(client, workspace_a, workspace_b):
    r = client.get("/api/channels", headers=workspace_a["owner"].headers())
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()}
    assert workspace_a["channel1_id"] in ids
    assert workspace_b["channel_id"] not in ids


def test_system_admin_sees_across_workspaces(client, system_admin, workspace_a, workspace_b):
    r = client.get("/api/workspaces", headers={"X-Api-Key": system_admin["api_key"]})
    assert r.status_code == 200
    slugs = {w["id"] for w in r.json()}
    assert workspace_a["workspace_id"] in slugs and workspace_b["workspace_id"] in slugs


def test_portfolio_route_rejects_foreign_workspace(client, workspace_a, workspace_b):
    r = client.post("/api/portfolio/route",
                    json={"workspace_id": workspace_b["workspace_id"], "topic": "AI"},
                    headers=workspace_a["owner"].headers())
    assert r.status_code == 403


# ---- credential scope isolation (§70-§71) -------------------------- #

def test_credential_scope_blocks_cross_brand_token():
    acc = PlatformAccount(id="acc1", platform="instagram_reel", account_name="A IG")
    acc.workspace_id = "ws-A"
    acc.brand_id = "brand-A"
    # correct scope: no raise
    assert_credential_scope(acc, expected_workspace="ws-A", expected_brand="brand-A",
                            expected_platform="instagram_reel")
    # wrong brand
    with pytest.raises(PublishError):
        assert_credential_scope(acc, expected_workspace="ws-A", expected_brand="brand-B")
    # wrong workspace
    with pytest.raises(PublishError):
        assert_credential_scope(acc, expected_workspace="ws-OTHER")
    # wrong platform
    with pytest.raises(PublishError):
        assert_credential_scope(acc, expected_platform="tiktok")


def test_credential_scope_allows_legacy_null_scope_when_unspecified():
    acc = PlatformAccount(id="acc2", platform="youtube_shorts", account_name="legacy")
    # legacy account: workspace_id/brand_id are None; no expectation passed -> ok
    assert_credential_scope(acc)
    # but if a workspace IS expected, a NULL-scoped legacy account is still allowed
    # (opt-in migration), while a DIFFERENT explicit scope is not
    assert_credential_scope(acc, expected_workspace="ws-A")
