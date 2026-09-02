from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

log = logging.getLogger("acf.publishing.crypto")

# Dev fallback key — used ONLY when ACF_MASTER_KEY is unset. Loud warning.
# Production MUST set ACF_MASTER_KEY (a base64 32-byte Fernet key) via the
# environment / secret manager. The key is never written to the database.
_DEV_SEED = b"acf-dev-master-key-not-for-production"


@lru_cache
def _fernet() -> Fernet:
    s = get_settings()
    key = s.acf_master_key
    if key:
        try:
            return Fernet(key if isinstance(key, bytes) else key.encode())
        except (ValueError, TypeError) as e:  # not a valid Fernet key
            raise RuntimeError(f"ACF_MASTER_KEY is not a valid Fernet key: {e}") from e
    log.warning(
        "ACF_MASTER_KEY is not set — using an insecure DEV encryption key. "
        "Set ACF_MASTER_KEY in production."
    )
    dev = base64.urlsafe_b64encode(hashlib.sha256(_DEV_SEED).digest())
    return Fernet(dev)


def encrypt_token(plaintext: str | None) -> str | None:
    if not plaintext:
        return None
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise RuntimeError("token decryption failed (wrong master key?)") from e


def mask_token(token: str | None) -> str:
    """abcd****1234 — safe for logs / API responses."""
    if not token:
        return ""
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}****{token[-4:]}"
