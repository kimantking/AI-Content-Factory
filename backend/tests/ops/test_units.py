from __future__ import annotations

import pytest

from app.ops.circuit_breaker import CircuitOpen, call_with_breaker, get_breaker
from app.ops.env import EnvValidationError, validate_environment
from app.ops.rate_limit import RateLimited, check as rl_check, classify_path
from app.ops.redaction import redact, redact_text
from app.ops.ssrf import SSRFBlocked, is_safe_url, require_safe_url
from app.ops.upload_security import (
    UploadRejected,
    has_path_traversal,
    safe_filename,
    validate_upload,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200


# ---- secret redaction ------------------------------------------------- #

def test_redaction_keys_and_values_and_nesting():
    obj = {
        "access_token": "ya29.abc",
        "nested": {"refresh_token": "r-123", "ok": "hello"},
        "list": [{"api_key": "sk-XXXX"}],
        "note": "call with Authorization: Bearer abcdefghijklmnop then done",
        "dsn": "postgresql://u:supersecret@db:5432/x",
    }
    r = redact(obj)
    assert r["access_token"] == "***REDACTED***"
    assert r["nested"]["refresh_token"] == "***REDACTED***"
    assert r["nested"]["ok"] == "hello"
    assert r["list"][0]["api_key"] == "***REDACTED***"
    assert "Bearer abcdefghijklmnop" not in r["note"]
    assert "supersecret" not in r["dsn"]


def test_redact_text_catches_jwt_and_fernet():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghij"
    assert redact_text(jwt) == "***REDACTED***"
    assert redact_text("gAAAAABm" + "x" * 60) == "***REDACTED***"


# ---- env validation ------------------------------------------------- #

def test_env_validation_blocks_bad_production(_ops_defaults):
    s = _ops_defaults
    s.app_env = "production"
    s.secret_key = None
    s.acf_master_key = None
    with pytest.raises(EnvValidationError):
        validate_environment(strict=True)
    # fix it -> only warnings
    s.secret_key = "x" * 32
    s.acf_master_key = "b" * 44
    s.cors_allow_origins = ["https://app.example.com"]
    s.oauth_callback_base_url = "https://api.example.com"
    s.public_base_url = "https://api.example.com"
    validate_environment(strict=True)   # no raise


def test_env_validation_rejects_bad_numbers(_ops_defaults):
    _ops_defaults.backup_retention_days = -5
    problems = validate_environment(strict=False)
    assert any("backup_retention_days" in p for p in problems)


# ---- SSRF ------------------------------------------------------------ #

@pytest.mark.parametrize("url", [
    "http://localhost/x", "http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5/", "http://192.168.1.1/", "file:///etc/passwd",
    "gopher://evil/", "http://metadata.google.internal/",
])
def test_ssrf_blocks_dangerous(url):
    ok, _reason = is_safe_url(url)
    assert ok is False


def test_ssrf_allows_public_and_allowlist(_ops_defaults):
    ok, _ = is_safe_url("https://www.googleapis.com/youtube/v3/videos")
    assert ok is True
    _ops_defaults.ssrf_allow_hosts = ["internal-cdn.local"]
    ok2, _ = is_safe_url("https://internal-cdn.local/asset.mp4")
    assert ok2 is True
    with pytest.raises(SSRFBlocked):
        require_safe_url("http://127.0.0.1:8000/")


# ---- upload security --------------------------------------------- #

def test_upload_magic_bytes_and_declared_mismatch():
    assert validate_upload(PNG, declared_mime="image/png")["mime"] == "image/png"
    with pytest.raises(UploadRejected):
        validate_upload(PNG, declared_mime="application/pdf")     # declared contradicts bytes
    with pytest.raises(UploadRejected):
        validate_upload(b"MZ\x90\x00rest is an exe")              # disallowed type
    with pytest.raises(UploadRejected):
        validate_upload(JPEG, max_size=10)                        # oversized


def test_safe_filename_and_traversal():
    assert has_path_traversal("../../etc/passwd")
    assert has_path_traversal("/abs/path")
    assert not has_path_traversal("normal.png")
    n = safe_filename("../../evil.png")
    assert "/" not in n and "\\" not in n and n.endswith(".png") and ".." not in n


# ---- circuit breaker ------------------------------------------- #

def test_circuit_breaker_opens_and_recovers(_ops_defaults):
    _ops_defaults.provider_breaker_threshold = 3
    _ops_defaults.provider_breaker_cooldown_s = 0.2

    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("provider down")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            call_with_breaker("img-provider", boom)
    # now OPEN -> fast fail, fn not called
    with pytest.raises(CircuitOpen):
        call_with_breaker("img-provider", boom)
    assert calls["n"] == 3

    # fallback path instead of raising
    out = call_with_breaker("img-provider", boom, on_open=lambda: "fallback")
    assert out == "fallback"

    import time

    time.sleep(0.25)  # cooldown -> HALF_OPEN, one probe allowed; success closes it
    assert call_with_breaker("img-provider", lambda: "ok") == "ok"
    assert get_breaker("img-provider").state == "CLOSED"


# ---- rate limiter ------------------------------------------- #

def test_rate_limiter_bursts_then_blocks():
    for _ in range(10):
        rl_check("auth", "1.2.3.4")            # capacity 10
    with pytest.raises(RateLimited) as ei:
        rl_check("auth", "1.2.3.4")
    assert ei.value.retry_after >= 0
    rl_check("auth", "9.9.9.9")                # different client unaffected


def test_classify_path():
    assert classify_path("/webhooks/instagram", "POST") == "webhook"
    assert classify_path("/metrics", "GET") == "metrics"
    assert classify_path("/api/campaigns", "POST") == "campaign_create"
    assert classify_path("/api/autopilot/scan", "POST") == "autopilot"
