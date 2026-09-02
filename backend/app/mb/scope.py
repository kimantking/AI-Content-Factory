"""Tenant / resource authorization (§4, §70-§72).

Every workspace-scoped resource is fetched *and* checked here. Knowing an id is
never enough — the row's workspace_id must match the caller's membership (system
admins pass).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models_mb import Brand, Channel, Workspace


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_workspace(db: Session, ctx, workspace_id: str) -> Workspace:
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(404, "workspace not found")
    ctx.assert_workspace(ws.id)
    return ws


def get_brand(db: Session, ctx, brand_id: str) -> Brand:
    b = db.get(Brand, brand_id)
    if b is None:
        raise HTTPException(404, "brand not found")
    ctx.assert_workspace(b.workspace_id)
    return b


def get_channel(db: Session, ctx, channel_id: str) -> Channel:
    c = db.get(Channel, channel_id)
    if c is None:
        raise HTTPException(404, "channel not found")
    ctx.assert_workspace(c.workspace_id)
    return c


def assert_same_workspace(*rows) -> None:
    """All rows must share a non-null workspace_id (defence in depth for joins)."""
    wss = {getattr(r, "workspace_id", None) for r in rows if r is not None}
    wss.discard(None)
    if len(wss) > 1:
        raise HTTPException(409, "resources span multiple workspaces")


def scoped_query(db: Session, model, ctx, *, workspace_id: str | None = None):
    """A query pre-filtered to workspaces the caller can see."""
    q = db.query(model)
    if ctx.is_system_admin and workspace_id is None:
        return q
    allowed = list(ctx.memberships.keys()) or ["__none__"]
    if workspace_id is not None:
        ctx.assert_workspace(workspace_id)
        allowed = [workspace_id]
    return q.filter(model.workspace_id.in_(allowed))
