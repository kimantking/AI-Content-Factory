from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from app.auth.service import add_member, create_user, hash_api_key, new_api_key
from app.db.base import session_scope
from app.db.models_mb import Brand, Channel, Workspace


@dataclass
class Actor:
    user_id: str
    api_key: str
    workspace_id: str

    def headers(self, workspace_id: str | None = None) -> dict:
        h = {"X-Api-Key": self.api_key}
        h["X-Workspace-Id"] = workspace_id or self.workspace_id
        return h


def _mk_user(db, email: str, *, system_admin=False) -> tuple[str, str]:
    u = create_user(db, email=email, is_system_admin=system_admin)
    raw = new_api_key()
    u.api_key_hash = hash_api_key(raw)
    db.flush()
    return u.id, raw


@pytest.fixture
def system_admin(_base_settings):
    with session_scope() as db:
        uid, key = _mk_user(db, f"sysadmin-{uuid.uuid4().hex[:6]}@x.io", system_admin=True)
    return {"user_id": uid, "api_key": key}


@pytest.fixture
def workspace_a(_base_settings):
    """A workspace with an OWNER + a VIEWER, one brand, two channels."""
    with session_scope() as db:
        w = Workspace(name="WS A", slug=f"ws-a-{uuid.uuid4().hex[:6]}",
                      daily_hard_budget_usd=100.0, objective="BALANCED")
        db.add(w); db.flush()
        owner_id, owner_key = _mk_user(db, f"owner-a-{uuid.uuid4().hex[:6]}@x.io")
        viewer_id, viewer_key = _mk_user(db, f"viewer-a-{uuid.uuid4().hex[:6]}@x.io")
        editor_id, editor_key = _mk_user(db, f"editor-a-{uuid.uuid4().hex[:6]}@x.io")
        add_member(db, workspace_id=w.id, user_id=owner_id, role="OWNER")
        add_member(db, workspace_id=w.id, user_id=viewer_id, role="VIEWER")
        add_member(db, workspace_id=w.id, user_id=editor_id, role="EDITOR")
        b = Brand(workspace_id=w.id, name="Brand A", slug="brand-a",
                  daily_hard_budget_usd=70.0, primary_objective="BALANCED",
                  risk_policy={"blocked_topics": ["도박"]})
        db.add(b); db.flush()
        c1 = Channel(workspace_id=w.id, brand_id=b.id, name="A Shorts",
                     platform="youtube_shorts", channel_type="YOUTUBE_SHORTS",
                     primary_objective="GROWTH", daily_budget_usd=25.0, daily_max_posts=3,
                     status="ACTIVE", lifecycle="ACTIVE")
        c2 = Channel(workspace_id=w.id, brand_id=b.id, name="A TikTok",
                     platform="tiktok", channel_type="TIKTOK",
                     primary_objective="REVENUE", daily_budget_usd=20.0, daily_max_posts=2,
                     status="ACTIVE", lifecycle="WARMUP")
        db.add_all([c1, c2]); db.flush()
        ids = {"workspace_id": w.id, "brand_id": b.id, "channel1_id": c1.id, "channel2_id": c2.id,
               "owner": Actor(owner_id, owner_key, w.id),
               "viewer": Actor(viewer_id, viewer_key, w.id),
               "editor": Actor(editor_id, editor_key, w.id)}
    return ids


@pytest.fixture
def workspace_b(_base_settings):
    with session_scope() as db:
        w = Workspace(name="WS B", slug=f"ws-b-{uuid.uuid4().hex[:6]}", daily_hard_budget_usd=50.0)
        db.add(w); db.flush()
        uid, key = _mk_user(db, f"owner-b-{uuid.uuid4().hex[:6]}@x.io")
        add_member(db, workspace_id=w.id, user_id=uid, role="OWNER")
        b = Brand(workspace_id=w.id, name="Brand B", slug="brand-b", daily_hard_budget_usd=40.0)
        db.add(b); db.flush()
        c = Channel(workspace_id=w.id, brand_id=b.id, name="B Shorts", platform="youtube_shorts",
                    channel_type="YOUTUBE_SHORTS", daily_budget_usd=15.0, status="ACTIVE",
                    lifecycle="ACTIVE")
        db.add(c); db.flush()
        ids = {"workspace_id": w.id, "brand_id": b.id, "channel_id": c.id,
               "owner": Actor(uid, key, w.id)}
    return ids


@pytest.fixture
def client(_base_settings):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_authenforced(_base_settings):
    _base_settings.auth_enforce = True
    from fastapi.testclient import TestClient

    from app.main import app

    yield TestClient(app, raise_server_exceptions=False)
    _base_settings.auth_enforce = False
