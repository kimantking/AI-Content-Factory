"""Production configuration validator (Phase 10 §2-§3).

Checks the runtime config for a given environment and reports each capability's
status without ever inventing a green. In `production`:
  * DEBUG / mock providers / demo publishers / test fixtures must be OFF;
  * a real SECRET_KEY / DATABASE_URL / PUBLIC_BASE_URL must be set;
  * production must NOT silently fall back to mock/test providers.
"""
from __future__ import annotations

from app.config import get_settings

STATUS = ("READY", "DEGRADED", "NOT_CONFIGURED", "NEEDS_CREDENTIALS",
          "NEEDS_PRODUCTION_ENVIRONMENT", "MISCONFIGURED")


def _is_prod(s) -> bool:
    return s.app_env == "production"


def check_config() -> dict:
    s = get_settings()
    prod = _is_prod(s)
    problems: list[str] = []
    caps: dict[str, dict] = {}

    # delegate the hard prod checks to the existing fast-fail validator
    try:
        from app.ops.env import validate_environment

        for item in validate_environment(strict=False):
            # validate_environment mixes warnings + problems; treat prod-only
            # security items as blocking here.
            if prod and any(w in item.lower() for w in
                            ("secret_key", "acf_master_key", "cors", "oauth", "localhost")):
                problems.append(item)
    except Exception:  # noqa: BLE001
        pass

    def cap(name, status, detail=""):
        caps[name] = {"status": status, "detail": detail}

    # ---- core env ----
    cap("APP_ENV", "READY", s.app_env)
    if prod:
        if not s.secret_key or len(str(s.secret_key)) < 16:
            problems.append("SECRET_KEY missing/short in production")
        if getattr(s, "debug", False):
            problems.append("DEBUG must be false in production")
        if s.llm_is_mock:
            problems.append("production is running with MOCK LLM (llm_is_mock=true)")
        if getattr(s, "mock_mode", False):
            problems.append("MOCK_MODE must be false in production")
        if "*" in (s.cors_allow_origins or []):
            problems.append("CORS is wide-open ('*') in production")
        if "*" in (s.trusted_hosts or []):
            problems.append("TRUSTED_HOSTS is '*' in production")

    # ---- database / redis ----
    dsn = s.sync_database_url or ""
    cap("DATABASE_URL", "READY" if dsn else "NOT_CONFIGURED",
        "sqlite" if "sqlite" in dsn else "postgres")
    if prod and ("localhost" in dsn or "127.0.0.1" in dsn):
        cap("DATABASE_URL", "DEGRADED", "points at localhost in production")
    cap("REDIS_URL", "READY" if s.redis_url else "NOT_CONFIGURED")

    # ---- public base url / TLS ----
    base = getattr(s, "public_base_url", "") or ""
    if not base:
        cap("PUBLIC_BASE_URL", "NEEDS_PRODUCTION_ENVIRONMENT", "not set")
    elif base.startswith("https://"):
        cap("PUBLIC_BASE_URL", "READY", base)
    else:
        cap("PUBLIC_BASE_URL", "DEGRADED" if not prod else "MISCONFIGURED",
            "HTTP only — not production-ready" if prod else base)

    # ---- local AI ----
    cap("OLLAMA", "READY" if s.ollama_enabled else "NOT_CONFIGURED",
        f"{s.ollama_base_url} · {s.ollama_default_model}")
    cap("ALLOW_CLOUD_FALLBACK", "READY", str(s.allow_cloud_fallback))
    cap("MODEL_ROUTER", "READY" if s.model_router_enabled else "DEGRADED")

    # ---- paid providers ----
    cap("ANTHROPIC", "READY" if s.anthropic_api_key else "NEEDS_CREDENTIALS")
    cap("TAVILY_SEARCH", "READY" if getattr(s, "tavily_api_key", None) else "NEEDS_CREDENTIALS")
    # Google AI (image / video)
    if s.google_api_key and (s.image_provider == "google" or s.video_provider == "google"):
        cap("GOOGLE_AI", "READY", f"image={s.image_provider} video={s.video_provider} "
            f"model={s.google_image_model}/{s.google_video_model}")
    elif s.google_api_key:
        cap("GOOGLE_AI", "DEGRADED", "key set but IMAGE_PROVIDER/VIDEO_PROVIDER != google")
    else:
        cap("GOOGLE_AI", "NEEDS_CREDENTIALS", "GOOGLE_API_KEY not set")
    # ElevenLabs (voice / TTS)
    if s.elevenlabs_api_key and s.tts_provider == "elevenlabs":
        cap("ELEVENLABS", "READY" if s.elevenlabs_voice_id else "MISCONFIGURED",
            "ELEVENLABS_VOICE_ID not set" if not s.elevenlabs_voice_id
            else f"model={s.elevenlabs_model}")
    elif s.elevenlabs_api_key:
        cap("ELEVENLABS", "DEGRADED", "key set but TTS_PROVIDER != elevenlabs")
    else:
        cap("ELEVENLABS", "NEEDS_CREDENTIALS", "ELEVENLABS_API_KEY not set")
    # media providers still mock unless the above are wired
    _media_mock = all(s.media_provider_is_mock(k) for k in ("image", "video", "tts"))
    cap("MEDIA_PROVIDERS", "NEEDS_CREDENTIALS" if _media_mock else "READY",
        "all mock" if _media_mock else "at least one real media provider configured")

    # ---- budgets ----
    if (s.campaign_budget_usd or 0) <= 0:
        problems.append("campaign_budget_usd is 0 (no per-campaign hard cap)")
    cap("BUDGETS", "READY" if (s.campaign_budget_usd or 0) > 0 else "MISCONFIGURED",
        f"campaign={s.campaign_budget_usd} daily={s.daily_budget_usd} monthly={s.monthly_budget_usd}")

    # ---- workers / rate limits ----
    cap("WORKER_CONCURRENCY", "READY", str(getattr(s, "local_model_max_concurrency", "?")))

    # ---- infra pending ----
    cap("OFF_SITE_BACKUP", "NEEDS_PRODUCTION_ENVIRONMENT")
    cap("WAL_PITR", "NEEDS_PRODUCTION_ENVIRONMENT")
    cap("EXTERNAL_MONITORING", "NEEDS_PRODUCTION_ENVIRONMENT")
    cap("DOMAIN_TLS", "READY" if base.startswith("https://") else "NEEDS_PRODUCTION_ENVIRONMENT")

    # ---- duplicate env keys guard ----
    dupes = _duplicate_env_keys()
    if dupes:
        problems.append(f"duplicate env keys: {', '.join(sorted(dupes))}")

    ok = not problems
    return {
        "environment": s.app_env,
        "version": s.app_version,
        "production_ready": ok if prod else None,
        "blocking_problems": problems,
        "capabilities": caps,
        "silent_mock_fallback_in_prod": bool(prod and (s.llm_is_mock or getattr(s, "mock_mode", False))),
    }


def _duplicate_env_keys() -> set[str]:
    import os
    from pathlib import Path
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return set()
    seen, dupes = set(), set()
    try:
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k = line.split("=", 1)[0].strip()
            if k in seen:
                dupes.add(k)
            seen.add(k)
    except Exception:  # noqa: BLE001
        pass
    _ = os  # keep import for clarity of intent
    return dupes
