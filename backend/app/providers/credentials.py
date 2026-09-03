"""Provider credential vault — encrypted API keys for the cloud providers.

Reuses the existing Fernet box (`app.publishing.crypto`, keyed by ACF_MASTER_KEY)
that already protects SNS OAuth tokens. NO new secret-storage system.

Resolution order for a usable key:
    1. workspace-scoped `provider_credentials` row
    2. instance-level `provider_credentials` row  (workspace_id == "")
    3. the `.env` / settings value  (backward compatible — existing deployments)

Only `last4` + health metadata ever leave this module. The plaintext key is
returned solely to the probe / adapter code inside the backend process.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.config import get_settings
from app.db.base import session_scope
from app.db.models_p11 import KEYED_PROVIDERS, ProviderCredential
from app.publishing.crypto import decrypt_token, encrypt_token, mask_token

_ENV_ATTR = {
    "anthropic": "anthropic_api_key",
    "tavily": "tavily_api_key",
    "google": "google_api_key",
    "elevenlabs": "elevenlabs_api_key",
}

_KEY_PREFIX = {
    "elevenlabs": ("sk_",),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_ws(workspace_id: str | None) -> str:
    return workspace_id or ""


def _valid(provider: str) -> None:
    if provider not in KEYED_PROVIDERS:
        raise ValueError(f"unknown keyed provider: {provider!r}")


def _last4(key: str) -> str:
    return key[-4:] if key and len(key) >= 4 else ""


def validate_key(provider: str, api_key: str) -> str:
    """Normalize a key and reject identifiers pasted in place of secrets."""
    _valid(provider)
    key = (api_key or "").strip()
    if len(key) < 8:
        raise ValueError("API key looks too short")
    prefixes = _KEY_PREFIX.get(provider, ())
    if prefixes and not key.startswith(prefixes):
        expected = " or ".join(prefixes)
        if provider == "elevenlabs":
            raise ValueError(
                "ElevenLabs API Key ID는 사용할 수 없습니다. "
                f"Secret API Key({expected}로 시작)를 입력하세요."
            )
        raise ValueError(f"{provider} API key must start with {expected}")
    return key


# --------------------------------------------------------------------------- #
#  read
# --------------------------------------------------------------------------- #

def get_key(provider: str, *, workspace_id: str | None = None) -> str | None:
    """A usable plaintext key, or None. DB (workspace → instance) then .env."""
    _valid(provider)
    ws = _norm_ws(workspace_id)
    with session_scope() as s:
        row = s.get(ProviderCredential, (provider, ws))
        if row is None and ws:
            row = s.get(ProviderCredential, (provider, ""))
        enc = row.api_key_encrypted if row else None
    if enc:
        return decrypt_token(enc)
    return getattr(get_settings(), _ENV_ATTR[provider], None) or None


def key_source(provider: str, *, workspace_id: str | None = None) -> str:
    """'workspace' | 'instance' | 'env' | 'none' — for diagnostics, never a value."""
    _valid(provider)
    ws = _norm_ws(workspace_id)
    with session_scope() as s:
        if ws:
            r = s.get(ProviderCredential, (provider, ws))
            if r and r.api_key_encrypted:
                return "workspace"
        r = s.get(ProviderCredential, (provider, ""))
        if r and r.api_key_encrypted:
            return "instance"
    return "env" if getattr(get_settings(), _ENV_ATTR[provider], None) else "none"


def describe(provider: str, *, workspace_id: str | None = None) -> dict:
    """Non-secret view for the API / dashboard."""
    _valid(provider)
    ws = _norm_ws(workspace_id)
    src = key_source(provider, workspace_id=workspace_id)
    with session_scope() as s:
        row = s.get(ProviderCredential, (provider, ws))
        if row is None and ws:
            row = s.get(ProviderCredential, (provider, ""))
        env_last4 = ""
        if src == "env":
            ev = getattr(get_settings(), _ENV_ATTR[provider], None) or ""
            env_last4 = _last4(ev)
        d = {
            "provider": provider,
            "configured": src != "none",
            "key_source": src,
            "last4": (row.last4 if row and row.api_key_encrypted else env_last4),
            "status": (row.status if row else ("CONFIGURED" if src == "env" else "NOT_CONFIGURED")),
            "configured_at": _iso(row.configured_at) if row else None,
            "last_checked_at": _iso(row.last_checked_at) if row else None,
            "last_success_at": _iso(row.last_success_at) if row else None,
            "last_error_code": (row.last_error_code if row else ""),
            "meta": dict(row.meta or {}) if row else {},
        }
    return d


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# --------------------------------------------------------------------------- #
#  write
# --------------------------------------------------------------------------- #

def set_key(provider: str, api_key: str, *, workspace_id: str | None = None,
            actor: str = "user") -> dict:
    api_key = validate_key(provider, api_key)
    ws = _norm_ws(workspace_id)
    with session_scope() as s:
        row = s.get(ProviderCredential, (provider, ws))
        if row is None:
            row = ProviderCredential(provider=provider, workspace_id=ws)
            s.add(row)
        row.api_key_encrypted = encrypt_token(api_key)
        row.last4 = _last4(api_key)
        row.status = "CONFIGURED"
        row.configured_at = _now()
        row.last_checked_at = None
        row.last_success_at = None
        row.last_error_code = ""
        row.updated_by = actor
    return describe(provider, workspace_id=workspace_id)


def delete_key(provider: str, *, workspace_id: str | None = None, actor: str = "user") -> dict:
    _valid(provider)
    ws = _norm_ws(workspace_id)
    with session_scope() as s:
        row = s.get(ProviderCredential, (provider, ws))
        if row is not None:
            s.delete(row)
    return describe(provider, workspace_id=workspace_id)


def record_probe(provider: str, *, ok: bool, status: str, error_code: str = "",
                 meta_patch: dict | None = None, workspace_id: str | None = None,
                 actor: str = "user") -> dict:
    """Persist the outcome of a live probe. Never stores a secret."""
    _valid(provider)
    ws = _norm_ws(workspace_id)
    with session_scope() as s:
        row = s.get(ProviderCredential, (provider, ws))
        if row is None and ws:
            row = s.get(ProviderCredential, (provider, ""))
        if row is None:
            # env-only key — materialise an instance-level row to carry health
            row = ProviderCredential(provider=provider, workspace_id="", status="CONFIGURED")
            s.add(row)
        row.last_checked_at = _now()
        row.status = status
        row.last_error_code = "" if ok else (error_code or "ERROR")
        if ok:
            row.last_success_at = _now()
        if meta_patch:
            m = dict(row.meta or {})
            m.update(meta_patch)
            row.meta = m
        row.updated_by = actor
    return describe(provider, workspace_id=workspace_id)


def set_meta(provider: str, patch: dict, *, workspace_id: str | None = None,
             actor: str = "user") -> dict:
    _valid(provider)
    ws = _norm_ws(workspace_id)
    with session_scope() as s:
        row = s.get(ProviderCredential, (provider, ws))
        if row is None:
            row = ProviderCredential(provider=provider, workspace_id=ws, status="NOT_CONFIGURED")
            s.add(row)
        m = dict(row.meta or {})
        m.update(patch)
        row.meta = m
        row.updated_by = actor
    return describe(provider, workspace_id=workspace_id)


def mask(key: str | None) -> str:
    return mask_token(key)
