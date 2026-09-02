from __future__ import annotations

import pytest

_OPS_KEYS = [
    "app_env", "app_version", "secret_key", "acf_master_key",
    "cors_allow_origins", "trusted_hosts",
    "oauth_callback_base_url", "public_base_url", "rate_limit_enabled", "ssrf_enforce",
    "ssrf_allow_hosts", "backup_dir", "backup_retention_days", "backup_encryption_key",
    "provider_breaker_threshold", "provider_breaker_cooldown_s", "provider_breaker_probes",
    "queue_backpressure_warn", "queue_backpressure_hold", "worker_heartbeat_stale_s",
    "job_lease_seconds", "cost_anomaly_factor", "max_request_bytes", "max_upload_bytes",
    "autopilot_emergency_stop",
]


@pytest.fixture(autouse=True)
def _ops_defaults(_base_settings, tmp_path):
    s = _base_settings
    saved = {k: getattr(s, k) for k in _OPS_KEYS}
    s.app_env = "test"
    s.backup_dir = str(tmp_path / "backups")
    s.rate_limit_enabled = True
    s.ssrf_enforce = True
    yield s
    for k, v in saved.items():
        setattr(s, k, v)


@pytest.fixture(autouse=True)
def _reset_ops_state():
    from app.ops import circuit_breaker, metrics, rate_limit
    from app.ops.runtime_flags import _CACHE

    circuit_breaker.reset_for_tests()
    metrics.reset_for_tests()
    rate_limit.reset_for_tests()
    _CACHE.clear()
    yield
    circuit_breaker.reset_for_tests()
    rate_limit.reset_for_tests()
    _CACHE.clear()
