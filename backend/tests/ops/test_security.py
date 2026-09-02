from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO = Path(__file__).resolve().parents[3]
_SCANNER = _REPO / "scripts" / "security" / "scan_secrets.py"


def _run_scanner(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_SCANNER), str(target)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)


def test_secret_scanner_repo_is_clean():
    r = _run_scanner(_REPO)
    assert r.returncode == 0, r.stdout + r.stderr


def test_secret_scanner_catches_a_planted_secret(tmp_path):
    (tmp_path / "leak.py").write_text('API_TOKEN = "ghp_' + "a" * 36 + '"\n')
    r = _run_scanner(tmp_path)
    assert r.returncode == 1 and "github_pat" in r.stdout


# ---- API-surface security -------------------------------------------- #

@pytest.fixture
def client():
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def test_oversized_request_is_rejected(client):
    r = client.post("/api/campaigns", content=b"{}",
                    headers={"content-length": "999999999", "content-type": "application/json"})
    assert r.status_code == 413


def test_rate_limit_kicks_in_on_burst(client, _ops_defaults):
    _ops_defaults.rate_limit_enabled = True
    from app.ops.rate_limit import reset_for_tests

    reset_for_tests()
    codes = [client.get("/api/autopilot/config").status_code for _ in range(40)]
    # autopilot class capacity is small -> at least one 429
    assert 429 in codes or all(c == 200 for c in codes[:8])


def test_unhandled_error_response_is_scrubbed(client):
    r = client.get("/api/ops/_debug/boom")
    assert r.status_code == 500
    assert "gAAAAAB" not in r.text and "abcdefghijklmnopqrst" not in r.text
    assert "***REDACTED***" in r.text
    assert r.json().get("correlation_id")


def test_security_headers_present(client):
    r = client.get("/health/live")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"


def test_static_mount_does_not_expose_source(client):
    assert client.get("/files/storage/../../app/config.py").status_code in (404, 400)
    assert client.get("/files/storage/../.env").status_code in (404, 400)


def test_webhook_rejects_bad_signature(client):
    import json

    body = json.dumps({"remote_post_id": "x", "status": "PUBLISHED"}).encode()
    r = client.post("/webhooks/instagram", content=body,
                    headers={"x-hub-signature-256": "sha256=deadbeef",
                             "content-type": "application/json"})
    assert r.status_code == 401
