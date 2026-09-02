"""Phase 10 §2-§3 — production config validator. Never invents a green; flags a
production env that would silently fall back to mock/test providers."""
from __future__ import annotations

import pytest

from app.config import get_settings
from app.ops.config_check import check_config

pytestmark = [pytest.mark.phase10]

_SAVE = ("app_env", "mock_mode", "secret_key", "public_base_url",
         "cors_allow_origins", "trusted_hosts", "acf_master_key", "oauth_callback_base_url")


@pytest.fixture(autouse=True)
def _restore_env():
    s = get_settings()
    saved = {k: getattr(s, k, None) for k in _SAVE}
    yield
    for k, v in saved.items():
        setattr(s, k, v)


def test_test_env_reports_capabilities_without_claiming_prod_ready():
    r = check_config()
    assert r["environment"] == "test"
    assert r["production_ready"] is None            # not a prod env -> no verdict
    assert r["capabilities"]["ANTHROPIC"]["status"] == "NEEDS_CREDENTIALS"
    assert r["capabilities"]["MEDIA_PROVIDERS"]["status"] == "NEEDS_CREDENTIALS"
    assert r["capabilities"]["OFF_SITE_BACKUP"]["status"] == "NEEDS_PRODUCTION_ENVIRONMENT"
    assert r["silent_mock_fallback_in_prod"] is False


def test_production_flags_silent_mock_fallback_and_missing_secret(_base_settings):
    _base_settings.app_env = "production"
    _base_settings.mock_mode = True          # <- would be a silent mock in prod
    _base_settings.secret_key = None
    r = check_config()
    assert r["production_ready"] is False
    assert r["silent_mock_fallback_in_prod"] is True
    probs = " ".join(r["blocking_problems"]).lower()
    assert "mock" in probs and "secret_key" in probs


def test_production_http_public_base_url_is_misconfigured(_base_settings):
    _base_settings.app_env = "production"
    _base_settings.secret_key = "a-strong-enough-secret-key"
    _base_settings.mock_mode = False
    _base_settings.public_base_url = "http://acf.example.com"
    r = check_config()
    assert r["capabilities"]["PUBLIC_BASE_URL"]["status"] == "MISCONFIGURED"
    assert r["capabilities"]["DOMAIN_TLS"]["status"] == "NEEDS_PRODUCTION_ENVIRONMENT"


def test_config_check_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app, raise_server_exceptions=False).get("/api/ops/config-check")
    assert r.status_code == 200
    assert "capabilities" in r.json()
