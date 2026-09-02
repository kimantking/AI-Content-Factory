"""AI Support Snapshot API (Phase 10). Read-only, RBAC-scoped, secret-redacted."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.auth.context import AuthContext
from app.auth.deps import current_user
from app.config import get_settings
from app.db.base import get_db
from app.support.snapshot import build_snapshot, snapshot_text

router = APIRouter(prefix="/api/support", tags=["support"])


def _scope(ctx: AuthContext, workspace_id: str | None) -> tuple[str | None, bool]:
    """A normal user is pinned to their own workspace; a system admin gets
    infra detail and may inspect any workspace."""
    admin = bool(getattr(ctx, "is_system_admin", False))
    if admin:
        return workspace_id, True
    ws = getattr(ctx, "workspace_id", None) or workspace_id
    if ws is not None:
        ctx.assert_workspace(ws)   # IDOR guard
    return ws, False


@router.get("/snapshot")
def snapshot(workspace_id: str | None = Query(None), campaign_id: str | None = Query(None),
             db: Session = Depends(get_db), ctx: AuthContext = Depends(current_user)):
    ws, admin = _scope(ctx, workspace_id)
    return build_snapshot(db, workspace_id=ws, admin=admin, campaign_id=campaign_id)


@router.get("/snapshot.txt", response_class=PlainTextResponse)
def snapshot_txt(workspace_id: str | None = Query(None), campaign_id: str | None = Query(None),
                 db: Session = Depends(get_db), ctx: AuthContext = Depends(current_user)):
    ws, admin = _scope(ctx, workspace_id)
    return snapshot_text(build_snapshot(db, workspace_id=ws, admin=admin, campaign_id=campaign_id))


@router.get("/version")
def version():
    s = get_settings()
    return {"product": "AI Content Factory", "version": s.app_version,
            "release_name": s.release_name, "environment": s.app_env}
