from __future__ import annotations

import logging

from app.config import get_settings

log = logging.getLogger("acf.ops.env")


class EnvValidationError(RuntimeError):
    pass


def validate_environment(*, strict: bool | None = None) -> list[str]:
    """Fail fast on a mis-configured production start. Platform API keys are NOT
    required — only used when that platform is used. Returns the list of
    warnings; raises EnvValidationError on a hard problem in production."""
    s = get_settings()
    strict = s.is_production if strict is None else strict
    problems: list[str] = []
    warnings: list[str] = []

    if s.is_production:
        if not s.secret_key:
            problems.append("SECRET_KEY is required in production")
        if not s.acf_master_key:
            problems.append("ACF_MASTER_KEY (token encryption) is required in production")
        if not s.database_url or "localhost" in s.database_url:
            warnings.append("DATABASE_URL points at localhost in production")
        if s.cors_allow_origins == ["*"]:
            problems.append("CORS_ALLOW_ORIGINS must not be '*' in production")
        if s.trusted_hosts == ["*"]:
            warnings.append("TRUSTED_HOSTS is '*' in production")
        if s.mock_mode:
            warnings.append("MOCK_MODE is on in production")
        if s.dry_run is False and s.platform_client == "mock":
            warnings.append("DRY_RUN off but platform_client is mock")
        if "localhost" in s.oauth_callback_base_url:
            problems.append("OAUTH_CALLBACK_BASE_URL is localhost in production (OAuth needs HTTPS)")
        if not s.public_base_url.startswith("https://"):
            warnings.append("PUBLIC_BASE_URL is not https in production")

    # sanity on numeric config regardless of env
    for key, val, ok in [
        ("autopilot_daily_budget_usd", s.autopilot_daily_budget_usd, s.autopilot_daily_budget_usd >= 0),
        ("autopilot_daily_hard_budget_usd", s.autopilot_daily_hard_budget_usd,
         s.autopilot_daily_hard_budget_usd >= 0),
        ("backup_retention_days", s.backup_retention_days, s.backup_retention_days > 0),
        ("render_max_concurrency", s.render_max_concurrency, s.render_max_concurrency >= 1),
        ("worker_heartbeat_stale_s", s.worker_heartbeat_stale_s, s.worker_heartbeat_stale_s > 0),
        ("job_lease_seconds", s.job_lease_seconds, s.job_lease_seconds > 0),
    ]:
        if not ok:
            problems.append(f"invalid config: {key}={val}")

    for w in warnings:
        log.warning("env warning: %s", w)

    if strict and problems:
        raise EnvValidationError("; ".join(problems))
    if problems:
        for p in problems:
            log.error("env problem: %s", p)
    return warnings + problems
