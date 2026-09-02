from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import require_system_admin
from app.auth.service import add_member, create_user, issue_api_key
from app.db.base import get_db
from app.db.models_mb import User, Workspace, WorkspaceMember

router = APIRouter(prefix="/api/admin", tags=["admin"])


class NewUser(BaseModel):
    email: str
    name: str = ""
    password: str | None = None
    is_system_admin: bool = False


@router.post("/users", status_code=201)
def create_user_ep(body: NewUser, db: Session = Depends(get_db),
                   _=Depends(require_system_admin)):
    if db.query(User).filter_by(email=body.email.lower().strip()).first():
        raise HTTPException(409, "email already exists")
    u = create_user(db, email=body.email, name=body.name, password=body.password,
                    is_system_admin=body.is_system_admin)
    return {"id": u.id, "email": u.email, "is_system_admin": u.is_system_admin}


@router.post("/users/{user_id}/api-key")
def rotate_key(user_id: str, db: Session = Depends(get_db), _=Depends(require_system_admin)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    raw = issue_api_key(db, u)
    return {"user_id": u.id, "api_key": raw, "note": "store this now — it is not shown again"}


@router.post("/users/{user_id}/memberships")
def add_membership(user_id: str, workspace_id: str = Body(..., embed=True),
                   role: str = Body(..., embed=True), db: Session = Depends(get_db),
                   _=Depends(require_system_admin)):
    if db.get(User, user_id) is None:
        raise HTTPException(404, "user not found")
    if db.get(Workspace, workspace_id) is None:
        raise HTTPException(404, "workspace not found")
    if role not in ("OWNER", "ADMIN", "EDITOR", "PUBLISHER", "ANALYST", "VIEWER"):
        raise HTTPException(400, "invalid role")
    existing = db.query(WorkspaceMember).filter_by(workspace_id=workspace_id, user_id=user_id).first()
    if existing:
        existing.role = role
        m = existing
    else:
        m = add_member(db, workspace_id=workspace_id, user_id=user_id, role=role)
    return {"id": m.id, "workspace_id": workspace_id, "user_id": user_id, "role": role}


@router.get("/users")
def list_users(db: Session = Depends(get_db), _=Depends(require_system_admin)):
    return [{"id": u.id, "email": u.email, "name": u.name,
             "is_system_admin": u.is_system_admin, "status": u.status}
            for u in db.query(User).order_by(User.created_at).all()]


def bootstrap_admin_if_configured() -> None:
    """Called at startup: if BOOTSTRAP_ADMIN_EMAIL + BOOTSTRAP_ADMIN_KEY are set
    and no such user exists, create a system-admin with that fixed API key.
    Convenience for local/first-run; production should still rotate the key."""
    from app.auth.service import hash_api_key
    from app.config import get_settings
    from app.db.base import session_scope

    s = get_settings()
    if not (s.bootstrap_admin_email and s.bootstrap_admin_key):
        return
    with session_scope() as db:
        u = db.query(User).filter_by(email=s.bootstrap_admin_email.lower().strip()).first()
        if u is None:
            u = create_user(db, email=s.bootstrap_admin_email, name="bootstrap-admin",
                            is_system_admin=True)
        u.is_system_admin = True
        u.api_key_hash = hash_api_key(s.bootstrap_admin_key)
