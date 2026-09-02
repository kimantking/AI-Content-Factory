from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.models import PlatformAccount
from app.publishing.base import PublishError, PublishErrorType
from app.publishing.capabilities import get_capability
from app.publishing.crypto import decrypt_token, encrypt_token
from app.publishing.oauth import refresh_token

# connection states
CONNECTED = "CONNECTED"
TOKEN_EXPIRING = "TOKEN_EXPIRING"
REFRESH_REQUIRED = "REFRESH_REQUIRED"
REAUTH_REQUIRED = "REAUTH_REQUIRED"
PERMISSION_MISSING = "PERMISSION_MISSING"
DISCONNECTED = "DISCONNECTED"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def connection_state(account: PlatformAccount) -> str:
    if not account.access_token_encrypted:
        return DISCONNECTED
    cap = get_capability(account.platform)
    have = set(account.scopes or [])
    if cap.required_scopes and not set(cap.required_scopes).issubset(have):
        return PERMISSION_MISSING
    exp = account.token_expires_at
    if exp is None:
        return CONNECTED
    exp = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
    now = _now()
    if exp <= now:
        return REFRESH_REQUIRED if account.refresh_token_encrypted else REAUTH_REQUIRED
    if exp - now <= timedelta(minutes=10):
        return TOKEN_EXPIRING
    return CONNECTED


def assert_credential_scope(account: PlatformAccount, *, expected_workspace: str | None = None,
                            expected_brand: str | None = None,
                            expected_platform: str | None = None) -> None:
    """Phase 6 §70-§71 — a token may only be used within its own workspace/brand/
    platform. Brand A's Instagram token must never be handed to Brand B's
    publisher. Legacy accounts with NULL scope are allowed only when no
    expectation is passed."""
    if expected_platform and account.platform != expected_platform:
        raise PublishError(PublishErrorType.AUTH_REVOKED,
                           f"credential platform mismatch: token={account.platform} expected={expected_platform}")
    acc_ws = getattr(account, "workspace_id", None)
    acc_brand = getattr(account, "brand_id", None)
    if expected_workspace is not None and acc_ws not in (None, expected_workspace):
        raise PublishError(PublishErrorType.AUTH_REVOKED,
                           "credential belongs to another workspace")
    if expected_brand is not None and acc_brand not in (None, expected_brand):
        raise PublishError(PublishErrorType.AUTH_REVOKED,
                           "credential belongs to another brand")


def ensure_valid(session, account: PlatformAccount, *, expected_workspace: str | None = None,
                 expected_brand: str | None = None, expected_platform: str | None = None) -> str:
    """Return a usable access token, refreshing once if needed. Never loops on
    AUTH errors — raises so the caller marks REAUTH_REQUIRED."""
    assert_credential_scope(account, expected_workspace=expected_workspace,
                            expected_brand=expected_brand, expected_platform=expected_platform)
    state = connection_state(account)
    if state in (CONNECTED, TOKEN_EXPIRING):
        return decrypt_token(account.access_token_encrypted)
    if state == PERMISSION_MISSING:
        raise PublishError(PublishErrorType.PERMISSION_MISSING,
                           f"{account.platform}: missing required scopes")
    if state == DISCONNECTED:
        raise PublishError(PublishErrorType.AUTH_REVOKED, f"{account.platform}: not connected")
    if state == REAUTH_REQUIRED:
        account.connection_status = REAUTH_REQUIRED
        raise PublishError(PublishErrorType.AUTH_REVOKED, f"{account.platform}: re-auth required")
    # REFRESH_REQUIRED -> exactly one refresh attempt
    try:
        bundle = refresh_token(account.platform, decrypt_token(account.refresh_token_encrypted))
    except PublishError:
        account.connection_status = REAUTH_REQUIRED
        raise
    account.access_token_encrypted = encrypt_token(bundle["access_token"])
    if bundle.get("refresh_token"):
        account.refresh_token_encrypted = encrypt_token(bundle["refresh_token"])
    account.token_expires_at = _now() + timedelta(seconds=bundle.get("expires_in", 3600))
    account.last_refresh_at = _now()
    account.connection_status = CONNECTED
    session.flush()
    return bundle["access_token"]


def health_check(session, account: PlatformAccount) -> dict:
    state = connection_state(account)
    account.connection_status = state
    account.last_health_check = _now()
    session.flush()
    cap = get_capability(account.platform)
    return {
        "platform": account.platform,
        "account_name": account.account_name,
        "connection_status": state,
        "publishing_status": cap.publishing_status,
        "app_review_required": cap.app_review_required,
        "account_requirement": cap.account_requirement,
        "integration_status": account.integration_status,
        "scopes_ok": (not cap.required_scopes)
        or set(cap.required_scopes).issubset(set(account.scopes or [])),
        "token_expires_at": account.token_expires_at.isoformat() if account.token_expires_at else None,
    }
