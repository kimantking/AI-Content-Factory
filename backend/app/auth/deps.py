from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.context import AuthContext
from app.auth.service import authenticate, memberships
from app.config import get_settings
from app.db.base import get_db


def _enforced() -> bool:
    """Auth is enforced in production/staging, or when AUTH_ENFORCE=true.
    In dev/test it is optional (so the existing suite runs unchanged), but a
    valid token is still honoured when supplied."""
    s = get_settings()
    return s.app_env in ("production", "staging") or bool(getattr(s, "auth_enforce", False))


def _ctx_from_user(db: Session, user) -> AuthContext:
    ms = memberships(db, user.id)
    return AuthContext(user_id=user.id, email=user.email,
                       is_system_admin=user.is_system_admin, memberships=ms)


def optional_auth(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> AuthContext | None:
    user = authenticate(db, authorization=authorization, x_api_key=x_api_key)
    return _ctx_from_user(db, user) if user else None


def current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> AuthContext:
    user = authenticate(db, authorization=authorization, x_api_key=x_api_key)
    if user is None:
        if _enforced():
            raise HTTPException(401, "authentication required")
        # dev/test: an anonymous system-admin context so existing flows keep working
        return AuthContext(user_id="dev-anonymous", email="dev@local",
                           is_system_admin=True, memberships={})
    return _ctx_from_user(db, user)


def require_system_admin(ctx: AuthContext = Depends(current_user)) -> AuthContext:
    if not ctx.is_system_admin:
        raise HTTPException(403, "system admin required")
    return ctx


def require_workspace(
    ctx: AuthContext = Depends(current_user),
    x_workspace_id: str | None = Header(default=None),
) -> AuthContext:
    """Resolve the active workspace from the X-Workspace-Id header, or the caller's
    sole membership. Endpoints that take an explicit workspace_id in the path/query/
    body should still call `scope.get_workspace(db, ctx, id)` for the row + check."""
    ws = x_workspace_id
    if ws is None:
        if len(ctx.memberships) == 1:
            ws = next(iter(ctx.memberships))
        elif ctx.is_system_admin:
            return ctx  # system admin without a header → scope set per-endpoint
        else:
            raise HTTPException(400, "X-Workspace-Id header required")
    ctx.assert_workspace(ws)
    ctx.workspace_id = ws
    ctx.role = ctx.role_in(ws)
    return ctx


def require_role(capability: str):
    """Dependency factory: require a capability in the active workspace."""

    def _dep(ctx: AuthContext = Depends(require_workspace)) -> AuthContext:
        ctx.require(capability)
        return ctx

    return _dep
