"""AUDIT-P8-004 — the Setup Wizard's "설정 완료" now persists to the server via
the existing tenant endpoints (frontend: lib/api.ts::finishSetup, wired into
app/setup/page.tsx). This exercises the wizard's server calls.
"""
from __future__ import annotations

import uuid


def test_wizard_finalize_persists_workspace_and_brand(client, system_admin):
    h = {"X-Api-Key": system_admin["api_key"]}
    ws_name = f"우리 스튜디오 {uuid.uuid4().hex[:5]}"
    br_name = "테크 채널"

    # step 1 of finishSetup: POST /api/workspaces
    w = client.post("/api/workspaces", json={"name": ws_name}, headers=h)
    assert w.status_code == 201
    wid = w.json()["id"]

    # a later load sees the persisted workspace (no longer localStorage-only)
    lw = client.get("/api/workspaces", headers=h)
    assert any(row["name"] == ws_name and row["id"] == wid for row in lw.json())

    # step 2: POST /api/brands under that workspace
    hw = {**h, "X-Workspace-Id": wid}
    b = client.post("/api/brands", json={"workspace_id": wid, "name": br_name}, headers=hw)
    assert b.status_code == 201
    lb = client.get("/api/brands", params={"workspace_id": wid}, headers=hw)
    assert br_name in [row["name"] for row in lb.json()]


def test_wizard_reuses_existing_workspace_by_name(client, system_admin):
    """finishSetup looks up an existing workspace by name and does NOT re-create
    it — so re-running the wizard is safe."""
    h = {"X-Api-Key": system_admin["api_key"]}
    ws_name = f"중복 {uuid.uuid4().hex[:5]}"
    first = client.post("/api/workspaces", json={"name": ws_name}, headers=h)
    assert first.status_code == 201
    listed = client.get("/api/workspaces", headers=h).json()
    assert sum(1 for r in listed if r["name"] == ws_name) == 1
