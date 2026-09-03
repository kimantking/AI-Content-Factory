from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy.orm import Session

from app.db.models_mb import User, WorkspaceMember

_ITER = 200_000


# ---- password + api-key hashing (stdlib pbkdf2) ------------------------- #

def hash_password(password: str, *, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITER)
    return f"pbkdf2_sha256${_ITER}${salt}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("pbkdf2_sha256$"):
        return False
    try:
        _, iters, salt, digest = stored.split("$", 3)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), digest)


def new_api_key() -> str:
    """The raw key shown to the user once. Format: acf_<40 hex>."""
    return "acf_" + secrets.token_hex(20)


def hash_api_key(raw: str) -> str:
    """Deterministic keyed hash so we can look up by hash without a per-row salt.
    The pepper is the app SECRET_KEY (or a stable dev default)."""
    from app.config import get_settings

    pepper = (get_settings().secret_key or "acf-dev-pepper").encode()
    return hmac.new(pepper, raw.encode(), hashlib.sha256).hexdigest()


# ---- user management ---------------------------------------------------- #

def create_user(db: Session, *, email: str, name: str = "", password: str | None = None,
                is_system_admin: bool = False) -> User:
    u = User(email=email.lower().strip(), name=name or email.split("@")[0],
             is_system_admin=is_system_admin,
             password_hash=hash_password(password) if password else None)
    db.add(u)
    db.flush()
    return u


def issue_api_key(db: Session, user: User) -> str:
    raw = new_api_key()
    user.api_key_hash = hash_api_key(raw)
    db.flush()
    return raw


def _bearer_or_key(authorization: str | None, x_api_key: str | None) -> str | None:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def authenticate(db: Session, *, authorization: str | None = None,
                 x_api_key: str | None = None) -> User | None:
    raw = _bearer_or_key(authorization, x_api_key)
    if not raw:
        return None
    u = db.query(User).filter_by(api_key_hash=hash_api_key(raw), status="ACTIVE").first()
    return u


def memberships(db: Session, user_id: str) -> dict[str, str]:
    """workspace_id -> role for this user."""
    return {m.workspace_id: m.role
            for m in db.query(WorkspaceMember).filter_by(user_id=user_id).all()}


def add_member(db: Session, *, workspace_id: str, user_id: str, role: str) -> WorkspaceMember:
    m = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
    db.add(m)
    db.flush()
    return m
