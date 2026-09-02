from __future__ import annotations

from app.auth.context import AuthContext, role_at_least
from app.auth.service import hash_api_key, hash_password, verify_password


# ---- hashing (stdlib pbkdf2, no dependency) --------------------------- #

def test_password_hash_roundtrip():
    h = hash_password("s3cret-pw")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("s3cret-pw", h) is True
    assert verify_password("wrong", h) is False
    assert verify_password("x", None) is False


def test_api_key_hash_is_deterministic_and_keyed(_base_settings):
    _base_settings.secret_key = "pepper-1"
    a = hash_api_key("acf_abc")
    assert a == hash_api_key("acf_abc")
    _base_settings.secret_key = "pepper-2"
    assert hash_api_key("acf_abc") != a          # pepper changes the hash


# ---- RBAC capability matrix ----------------------------------------- #

def test_role_ranking():
    assert role_at_least("OWNER", "ADMIN")
    assert role_at_least("EDITOR", "VIEWER")
    assert not role_at_least("VIEWER", "EDITOR")
    assert not role_at_least(None, "VIEWER")


def test_capability_gates():
    viewer = AuthContext(user_id="u", role="VIEWER", memberships={"w": "VIEWER"}, workspace_id="w")
    editor = AuthContext(user_id="u", role="EDITOR", memberships={"w": "EDITOR"}, workspace_id="w")
    admin = AuthContext(user_id="u", role="ADMIN", memberships={"w": "ADMIN"}, workspace_id="w")
    owner = AuthContext(user_id="u", role="OWNER", memberships={"w": "OWNER"}, workspace_id="w")
    sysadmin = AuthContext(user_id="u", is_system_admin=True)

    assert viewer.can("read") and not viewer.can("content.write")
    assert editor.can("content.write") and not editor.can("publish.approve")
    assert editor.can("campaign.create") and not editor.can("budget.write")
    assert admin.can("budget.write") and admin.can("channel.write") and not admin.can("workspace.manage")
    assert owner.can("workspace.manage") and owner.can("member.manage")
    assert sysadmin.can("workspace.manage")   # system admin bypasses


# ---- HTTP: admin / ops surfaces protected only when enforced --------- #

def test_ops_open_in_test_env_when_auth_not_enforced(client, _base_settings):
    assert _base_settings.auth_enforce is False
    assert client.get("/api/ops/status").status_code == 200


def test_ops_and_admin_protected_when_enforced(client_authenforced):
    assert client_authenforced.get("/api/ops/status").status_code == 401
    assert client_authenforced.get("/api/admin/users").status_code == 401
    assert client_authenforced.get("/admin").status_code in (401, 404)  # 404 if no such route


def test_enforced_ops_allows_valid_key(client_authenforced, system_admin):
    r = client_authenforced.get("/api/ops/status", headers={"X-Api-Key": system_admin["api_key"]})
    assert r.status_code == 200
    # a random key is rejected
    assert client_authenforced.get("/api/ops/status",
                                   headers={"X-Api-Key": "acf_not_a_real_key"}).status_code == 401


def test_admin_endpoints_require_system_admin(client, workspace_a):
    # workspace OWNER is not a system admin
    r = client.get("/api/admin/users", headers=workspace_a["owner"].headers())
    assert r.status_code == 403


def test_viewer_cannot_write_editor_can(client, workspace_a):
    body = {"workspace_id": workspace_a["workspace_id"], "name": "V Brand"}
    assert client.post("/api/brands", json=body,
                       headers=workspace_a["viewer"].headers()).status_code == 403
    # editor lacks brand.write (needs ADMIN) -> 403 too
    assert client.post("/api/brands", json=body,
                       headers=workspace_a["editor"].headers()).status_code == 403
    # owner can
    assert client.post("/api/brands", json=body,
                       headers=workspace_a["owner"].headers()).status_code == 201
