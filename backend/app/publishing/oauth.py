from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from app.config import get_settings
from app.db.models import OAuthState
from app.publishing.base import PublishError, PublishErrorType
from app.publishing.capabilities import get_capability

# Per-platform authorize endpoints (used to build the real consent URL). Token
# exchange against the real endpoints needs client credentials; without them the
# flow runs in MOCK mode and synthesises tokens for local/dev/testing.
_AUTHORIZE = {
    "youtube": "https://accounts.google.com/o/oauth2/v2/auth",
    "tiktok": "https://www.tiktok.com/v2/auth/authorize/",
    "instagram": "https://www.facebook.com/v21.0/dialog/oauth",
    "facebook": "https://www.facebook.com/v21.0/dialog/oauth",
    "threads": "https://threads.net/oauth/authorize",
    "x": "https://twitter.com/i/oauth2/authorize",
    "pinterest": "https://www.pinterest.com/oauth/",
    "linkedin": "https://www.linkedin.com/oauth/v2/authorization",
    "naver_blog": "https://nid.naver.com/oauth2.0/authorize",
    "naver_clip": "",
}


def _clients() -> dict:
    try:
        return json.loads(get_settings().oauth_client_json or "{}")
    except ValueError:
        return {}


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def start_authorization(session, platform: str, redirect_uri: str | None = None) -> dict:
    cap = get_capability(platform)
    if not cap.auth_supported:
        raise PublishError(PublishErrorType.PERMISSION_MISSING, f"{platform} has no OAuth")
    s = get_settings()
    redirect_uri = redirect_uri or f"{s.oauth_redirect_base}/api/publishing/oauth/{platform}/callback"
    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    session.add(OAuthState(state=state, platform=platform, redirect_uri=redirect_uri,
                           code_verifier=verifier))
    session.flush()

    client = _clients().get(platform, {})
    if not s.mock_mode and (not client.get("client_id") or not client.get("client_secret")):
        raise PublishError(
            PublishErrorType.PERMISSION_MISSING,
            f"{platform} OAuth client_id/client_secret가 설정되지 않았습니다",
        )
    params = {
        "response_type": "code",
        "client_id": client.get("client_id", "MOCK_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "scope": " ".join(cap.required_scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    base = _AUTHORIZE.get(platform) or ""
    url = f"{base}?{urlencode(params)}" if base else ""
    mode = "REAL" if client.get("client_id") and s.platform_client == "http" else "MOCK"
    return {"authorization_url": url, "state": state, "mode": mode, "redirect_uri": redirect_uri}


def _validate_state(session, state: str) -> OAuthState:
    row = session.query(OAuthState).filter_by(state=state).first()
    if row is None:
        raise PublishError(PublishErrorType.PERMISSION_MISSING, "invalid OAuth state (CSRF check failed)")
    if row.consumed:
        raise PublishError(PublishErrorType.PERMISSION_MISSING, "OAuth state already used")
    age = datetime.now(timezone.utc) - row.created_at.replace(tzinfo=timezone.utc)
    if age > timedelta(minutes=15):
        raise PublishError(PublishErrorType.PERMISSION_MISSING, "OAuth state expired")
    row.consumed = True
    session.flush()
    return row


def complete_authorization(session, platform: str, state: str, code: str) -> dict:
    row = _validate_state(session, state)
    if row.platform != platform:
        raise PublishError(PublishErrorType.PERMISSION_MISSING, "OAuth state platform mismatch")
    cap = get_capability(platform)
    client = _clients().get(platform, {})
    s = get_settings()
    if client.get("client_id") and client.get("client_secret") and s.platform_client == "http":
        # Real token exchange would go here (per-platform token endpoint). Not
        # wired without verified credentials -> signal clearly.
        raise PublishError(PublishErrorType.PERMISSION_MISSING,
                           "real OAuth token exchange not implemented — verified credentials required")
    if not s.mock_mode:
        raise PublishError(PublishErrorType.PERMISSION_MISSING,
                           "실사용 OAuth 토큰 교환 어댑터가 아직 연결되지 않았습니다")
    # Tests/dev mock only: synthesize a token bundle.
    return {
        "provider_mode": "MOCK",
        "access_token": f"mock-access-{secrets.token_hex(8)}",
        "refresh_token": f"mock-refresh-{secrets.token_hex(8)}",
        "expires_in": 3600,
        "scopes": list(cap.required_scopes),
        "account_id": f"mock-{platform}-acct",
        "account_name": f"Mock {platform.title()} Account",
    }


def refresh_token(platform: str, refresh_token_value: str | None) -> dict:
    if not refresh_token_value:
        raise PublishError(PublishErrorType.AUTH_REVOKED, "no refresh token — re-auth required")
    if refresh_token_value.startswith("revoked"):
        raise PublishError(PublishErrorType.AUTH_REVOKED, "refresh token revoked")
    s = get_settings()
    client = _clients().get(platform, {})
    if client.get("client_id") and s.platform_client == "http":
        raise PublishError(PublishErrorType.PERMISSION_MISSING,
                           "real token refresh not implemented — verified credentials required")
    if not s.mock_mode:
        raise PublishError(PublishErrorType.PERMISSION_MISSING,
                           "실사용 OAuth 토큰 갱신 어댑터가 아직 연결되지 않았습니다")
    return {
        "provider_mode": "MOCK",
        "access_token": f"mock-access-{secrets.token_hex(8)}",
        "refresh_token": refresh_token_value,
        "expires_in": 3600,
    }
