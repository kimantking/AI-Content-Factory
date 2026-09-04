"""Shared stdlib-only HTTP + error normalisation for the real media adapters
(Google AI, ElevenLabs). No new dependency — same approach as OllamaLLMProvider.

Adapters raise `ProviderError` with:
  * `error_type` — one of the existing retry-taxonomy values (so retry / gateway
    behaviour is unchanged): AUTH_ERROR | RATE_LIMIT | TIMEOUT | PROVIDER_ERROR
  * `provider_code` — the vendor-specific normalised code the AI Support Snapshot
    shows: GOOGLE_NOT_CONFIGURED / GOOGLE_AUTH_FAILED / GOOGLE_RATE_LIMITED /
    GOOGLE_PROVIDER_ERROR (and ELEVENLABS_*).
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from app.providers.errors import ProviderError

_RETRY_FOR = {"RATE_LIMIT", "TIMEOUT"}   # NOT_CONFIGURED / AUTH_FAILED are terminal


def provider_error(vendor: str, kind: str, message: str) -> ProviderError:
    """kind ∈ NOT_CONFIGURED | AUTH_FAILED | RATE_LIMITED | PROVIDER_ERROR | TIMEOUT."""
    v = vendor.upper()
    code = f"{v}_{kind}"
    et = {
        "NOT_CONFIGURED": "AUTH_ERROR",
        "AUTH_FAILED": "AUTH_ERROR",
        "RATE_LIMITED": "RATE_LIMIT",
        "TIMEOUT": "TIMEOUT",
        "PROVIDER_ERROR": "PROVIDER_ERROR",
    }.get(kind, "PROVIDER_ERROR")
    e = ProviderError(f"{code}: {message}"[:2000], error_type=et)
    e.provider_code = code           # type: ignore[attr-defined]
    e.vendor = vendor                # type: ignore[attr-defined]
    return e


def _kind_for_status(status: int) -> str:
    if status in (401, 403):
        return "AUTH_FAILED"
    if status == 429:
        return "RATE_LIMITED"
    return "PROVIDER_ERROR"


def _request(url: str, *, method: str, headers: dict, data: bytes | None,
             timeout: int, vendor: str) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode(errors="replace")[:500]
        except Exception:  # noqa: BLE001
            detail = ""
        raise provider_error(vendor, _kind_for_status(e.code),
                             f"HTTP {e.code} {detail}") from None
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise provider_error(vendor, "TIMEOUT", "request timed out") from None
        raise provider_error(vendor, "PROVIDER_ERROR", f"connection error: {reason}") from None


def http_json(url: str, *, method: str = "GET", headers: dict | None = None,
              body: dict | bytes | None = None, timeout: int = 60,
              vendor: str = "provider") -> dict:
    """One JSON request. Raises a normalised ProviderError on any failure.
    Never logs the URL or headers (they carry the key)."""
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        else:
            data = json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
    try:
        raw = _request(url, method=method, headers=hdrs, data=data,
                       timeout=timeout, vendor=vendor)
        return json.loads(raw or b"{}")
    except ValueError as e:
        raise provider_error(vendor, "PROVIDER_ERROR", f"invalid JSON response: {e}") from None


def http_bytes(url: str, *, method: str = "POST", headers: dict | None = None,
               body: dict | None = None, timeout: int = 60, vendor: str = "provider") -> bytes:
    """Same as http_json but returns the raw response body (audio / image bytes)."""
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    return _request(url, method=method, headers=hdrs, data=data,
                    timeout=timeout, vendor=vendor)
