"""Provider connection status for the dashboard / AI Support Snapshot.

Read-only. Never returns a secret value.

Status vocabulary:
  NOT_CONFIGURED  — no key / not enabled
  MOCK            — key present but MOCK_MODE (or a mock provider) is active,
                    so no real call will be made
  CONFIGURED      — key present, not mock, but no live call has verified it this
                    session (e.g. Anthropic / Tavily have no free health endpoint
                    and we do NOT spend a paid call to probe)
  CONNECTED       — a real, free, read-only probe/call SUCCEEDED this session
                    (Google: list models; ElevenLabs: list voices; Ollama:
                    /api/tags). Never claimed without a successful probe.
  DEGRADED        — reachable but not fully usable (e.g. model missing, service
                    up but disabled in config)
  AUTH_FAILED / ERROR — probe attempted and failed

No paid generation is ever performed here. Probes are cached briefly.
"""
from __future__ import annotations

import time

from app.config import get_settings

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 20.0


def _vault(provider: str) -> dict:
    """Credential-vault view (encrypted DB key + persisted probe health), or {}.
    Never returns a secret — only last4 / status / timestamps."""
    try:
        from app.providers import credentials as cred
        return cred.describe(provider)
    except Exception:  # noqa: BLE001
        return {}


def _resolved_key(provider: str, env_attr: str) -> str | None:
    try:
        from app.providers import credentials as cred
        return cred.get_key(provider)
    except Exception:  # noqa: BLE001
        return getattr(get_settings(), env_attr, None)


def _cached(key: str, fn):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    val = fn()
    _CACHE[key] = (time.time(), val)
    return val


def _connected_via_vault(v: dict) -> bool:
    return bool(v) and v.get("status") == "CONNECTED" and bool(v.get("last_success_at"))


_COMMON_FAILURES = frozenset({"AUTH_FAILED", "RATE_LIMITED", "BLOCKED", "ERROR"})


def _keyed_status(provider: str, env_attr: str, base: dict, *, mock: bool,
                  failures: set[str] | frozenset[str], connected_note: str,
                  mock_note: str = "key present but MOCK_MODE is on") -> dict:
    """Build the shared credential state without ever exposing the key."""
    v = _vault(provider)
    if v.get("last4"):
        base["last4"] = v["last4"]
    if not _resolved_key(provider, env_attr):
        return {**base, "status": "NOT_CONFIGURED"}
    if _connected_via_vault(v):
        return {**base, "status": "CONNECTED", "key_present": True,
                "last_success_at": v["last_success_at"], "last_checked_at": v.get("last_checked_at"),
                "note": connected_note}
    if v.get("status") in failures:
        return {**base, "status": v["status"], "key_present": True,
                "last_error_code": v.get("last_error_code"),
                "last_checked_at": v.get("last_checked_at")}
    if mock:
        return {**base, "status": "MOCK", "key_present": True, "note": mock_note}
    return {**base, "status": "CONFIGURED", "key_present": True,
            "note": "key present; run [연결 확인] for a live probe"}


def _anthropic() -> dict:
    s = get_settings()
    base = {"provider": "anthropic", "role": "cloud LLM", "model": s.anthropic_model}
    return _keyed_status(
        "anthropic", "anthropic_api_key", base, mock=s.llm_is_mock,
        failures=_COMMON_FAILURES | {"BILLING", "MODEL_UNAVAILABLE", "NEEDS_WORKSPACE_ID"},
        connected_note="verified by a minimal live probe",
        mock_note="key present but MOCK_MODE is on — no paid call is made")


def _tavily() -> dict:
    s = get_settings()
    base = {"provider": "tavily", "role": "search"}
    return _keyed_status(
        "tavily", "tavily_api_key", base, mock=s.search_is_mock,
        failures=_COMMON_FAILURES | {"QUOTA"},
        connected_note="verified by a minimal live search probe")


def _ollama() -> dict:
    s = get_settings()
    base = {"provider": "ollama", "role": "local LLM",
            "enabled": s.ollama_enabled, "base_url": s.ollama_base_url,
            "default_model": s.ollama_default_model}
    try:
        from app.providers.ollama_llm import OllamaLLMProvider

        h = OllamaLLMProvider(base_url=s.ollama_base_url, model=s.ollama_default_model).health()
        reachable = h.get("status") in ("CONNECTED", "OK", "RUNNING", "READY", "UP")
        has = s.ollama_default_model in (h.get("models") or [])
    except Exception as e:  # noqa: BLE001
        reachable, has = False, False
        h = {"error": type(e).__name__}

    if not s.ollama_enabled:
        if reachable:
            return {**base, "status": "DEGRADED", "service_reachable": True,
                    "model_present": has,
                    "note": "Ollama service is reachable but OLLAMA_ENABLED=false; set it true to use it"}
        return {**base, "status": "NOT_CONFIGURED", "service_reachable": False}

    if not reachable:
        return {**base, "status": "ERROR", "service_reachable": False, "detail": h.get("error")}
    # a real /api/tags call succeeded -> CONNECTED (model present) or DEGRADED (model missing)
    return {**base, "status": "CONNECTED" if has else "DEGRADED",
            "service_reachable": True, "model_present": has}


def _google() -> dict:
    s = get_settings()
    v = _vault("google")
    used = {"image": s.image_provider == "google", "video": s.video_provider == "google"}
    base = {"provider": "google", "role": "image/video (Imagen/Veo)",
            "image_model": s.google_image_model, "video_model": s.google_video_model,
            "used_for": used}
    if v.get("last4"):
        base["last4"] = v["last4"]
    vm = v.get("meta") or {}
    if vm.get("image_capability") or vm.get("video_capability"):
        base["image_capability"] = vm.get("image_capability")
        base["video_capability"] = vm.get("video_capability")
    key = _resolved_key("google", "google_api_key")
    if not key:
        return {**base, "status": "NOT_CONFIGURED"}
    if _connected_via_vault(v):
        return {**base, "status": "CONNECTED", "key_present": True,
                "last_success_at": v["last_success_at"], "last_checked_at": v.get("last_checked_at"),
                "models_visible": vm.get("models_visible"),
                "note": "verified by GET /v1beta/models (no generation)"}
    if s.mock_mode:
        return {**base, "status": "MOCK", "key_present": True,
                "note": "key present but MOCK_MODE is on"}
    try:
        from app.providers.media.google_image import GoogleImageProvider

        h = GoogleImageProvider().health()   # GET /v1beta/models — free, read-only
        st = h.get("status", "ERROR")
        return {**base, "status": st if st in ("CONNECTED", "ERROR") else "CONFIGURED",
                "models_visible": h.get("models_visible"), "provider_code": h.get("provider_code"),
                "detail": h.get("detail")}
    except Exception as e:  # noqa: BLE001
        return {**base, "status": "ERROR",
                "provider_code": getattr(e, "provider_code", "GOOGLE_PROVIDER_ERROR"),
                "detail": str(e)[:160]}


def _elevenlabs() -> dict:
    s = get_settings()
    v = _vault("elevenlabs")
    vm = v.get("meta") or {}
    voice_id = vm.get("voice_id") or s.elevenlabs_voice_id
    base = {"provider": "elevenlabs", "role": "voice/TTS", "model": s.elevenlabs_model,
            "used_for_tts": s.tts_provider == "elevenlabs",
            "voice_id": voice_id, "voice_selected": bool(vm.get("voice_selected"))}
    if v.get("last4"):
        base["last4"] = v["last4"]
    key = _resolved_key("elevenlabs", "elevenlabs_api_key")
    if not key:
        return {**base, "status": "NOT_CONFIGURED"}
    if _connected_via_vault(v):
        st = "CONNECTED"
        return {**base, "status": st, "key_present": True,
                "voices": vm.get("voice_count"),
                "voice_selection_required": not bool(vm.get("voice_selected")),
                "last_success_at": v["last_success_at"], "last_checked_at": v.get("last_checked_at"),
                "note": "verified by GET /v1/voices (no synthesis)"}
    if v.get("status") in ("AUTH_FAILED", "RATE_LIMITED", "QUOTA", "BLOCKED", "ERROR"):
        return {**base, "status": v["status"], "key_present": True,
                "last_error_code": v.get("last_error_code"),
                "last_checked_at": v.get("last_checked_at")}
    if s.mock_mode:
        return {**base, "status": "MOCK", "key_present": True,
                "note": "key present but MOCK_MODE is on"}
    try:
        from app.providers.media.elevenlabs_tts import ElevenLabsTTSProvider

        h = ElevenLabsTTSProvider().health()  # GET /v1/voices — free, read-only
        st = h.get("status", "ERROR")
        if st == "CONNECTED" and s.elevenlabs_voice_id and h.get("configured_voice_present") is False:
            st = "DEGRADED"
        return {**base, "status": st, "voices": h.get("voices"),
                "configured_voice_present": h.get("configured_voice_present"),
                "provider_code": h.get("provider_code"), "detail": h.get("detail")}
    except Exception as e:  # noqa: BLE001
        return {**base, "status": "ERROR",
                "provider_code": getattr(e, "provider_code", "ELEVENLABS_PROVIDER_ERROR"),
                "detail": str(e)[:160]}


def provider_status(*, probe: bool = True) -> dict:
    """probe=False -> config-only, no network (never returns CONNECTED).
    probe=True  -> cached live read-only probes where a free one exists."""
    s = get_settings()
    if not probe:
        def _cfg(provider, env_attr, mock):
            v = _vault(provider)
            if _connected_via_vault(v):
                return "CONNECTED"
            if not _resolved_key(provider, env_attr):
                return "NOT_CONFIGURED"
            return "MOCK" if mock else (v.get("status") or "CONFIGURED")
        return {"providers": [
            {"provider": "anthropic", "status": _cfg("anthropic", "anthropic_api_key", s.llm_is_mock)},
            {"provider": "tavily", "status": _cfg("tavily", "tavily_api_key", s.search_is_mock)},
            {"provider": "google", "status": _cfg("google", "google_api_key", s.mock_mode)},
            {"provider": "elevenlabs", "status": _cfg("elevenlabs", "elevenlabs_api_key", s.mock_mode)},
            {"provider": "ollama",
             "status": ("NOT_CONFIGURED" if not s.ollama_enabled else "CONFIGURED")},
        ]}
    return {"providers": [
        _cached("anthropic", _anthropic),
        _cached("tavily", _tavily),
        _cached("google", _google),
        _cached("elevenlabs", _elevenlabs),
        _cached("ollama", _ollama),
    ]}
