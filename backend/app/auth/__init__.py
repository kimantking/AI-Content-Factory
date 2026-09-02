"""Phase 6 — Authentication, RBAC, and tenant-scope authorization.

Deliberately minimal and provider-agnostic: local users with a hashed password
and/or a hashed API key (stdlib pbkdf2 — no dependency). An external identity
provider can be added later behind `IdentityProvider` without touching callers.
"""
from __future__ import annotations

from app.auth.context import ROLE_RANK, AuthContext, role_at_least
from app.auth.deps import (
    current_user,
    optional_auth,
    require_role,
    require_system_admin,
    require_workspace,
)
from app.auth.service import (
    authenticate,
    hash_api_key,
    issue_api_key,
    new_api_key,
    verify_password,
)

__all__ = [
    "AuthContext",
    "ROLE_RANK",
    "role_at_least",
    "current_user",
    "optional_auth",
    "require_role",
    "require_system_admin",
    "require_workspace",
    "authenticate",
    "issue_api_key",
    "new_api_key",
    "hash_api_key",
    "verify_password",
]
