"""Explicit, minimal, safe live connection probes for the cloud providers.

This is the ONLY place a real cloud call is made outside the content pipeline.
It is deliberately independent of MOCK_MODE (the pipeline stays mocked) but it
still honours GLOBAL_PAID_PROVIDER_PAUSE for the two providers whose probe costs
a token (Anthropic, Tavily). Google / ElevenLabs probes are free read-only GETs.

NO media generation, NO long TTS, NO large search, NO large inference is ever
performed here. Every probe records its outcome via `credentials.record_probe`.
"""
from __future__ import annotations

from app.config import get_settings
from app.providers import credentials as cred

# normalised probe status vocabulary (superset of credential.status)
CONNECTED = "CONNECTED"
AUTH_FAILED = "AUTH_FAILED"
PERMISSION_REQUIRED = "PERMISSION_REQUIRED"
RATE_LIMITED = "RATE_LIMITED"
BILLING = "BILLING"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
QUOTA = "QUOTA"
BLOCKED = "BLOCKED"
NOT_CONFIGURED = "NOT_CONFIGURED"
NEEDS_WORKSPACE_ID = "NEEDS_WORKSPACE_ID"   # Anthropic identity-linked key
ERROR = "ERROR"


def _paid_paused() -> bool:
    try:
        from app.ops.runtime_flags import paid_provider_paused
        return paid_provider_paused()
    except Exception:  # noqa: BLE001
        return False


def _result(provider: str, status: str, *, detail: str = "", code: str = "",
            extra: dict | None = None, workspace_id: str | None = None) -> dict:
    ok = status == CONNECTED
    meta_patch = {"probe_detail": detail[:300]}
    if extra:
        meta_patch.update(extra)
    saved = cred.record_probe(provider, ok=ok, status=status,
                              error_code=code or (status if not ok else ""),
                              meta_patch=meta_patch, workspace_id=workspace_id)
    out = {"provider": provider, "status": status, "ok": ok, "detail": detail[:300]}
    if extra:
        out.update(extra)
    out["credential"] = saved
    return out


# --------------------------------------------------------------------------- #
#  Anthropic — 1 tiny inference (max_tokens=8), fixed prompt
# --------------------------------------------------------------------------- #

def _probe_anthropic(workspace_id: str | None) -> dict:
    s = get_settings()
    key = cred.get_key("anthropic", workspace_id=workspace_id)
    if not key:
        return _result("anthropic", NOT_CONFIGURED, detail="no API key", workspace_id=workspace_id)
    if _paid_paused():
        return _result("anthropic", BLOCKED,
                       detail="GLOBAL_PAID_PROVIDER_PAUSE is active", code="PAID_PAUSED",
                       workspace_id=workspace_id)
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        return _result("anthropic", ERROR, detail=f"anthropic sdk missing: {e}",
                       workspace_id=workspace_id)

    model = s.anthropic_model
    ws_id = (getattr(s, "anthropic_workspace_id", "") or "").strip()
    try:
        kw: dict = {"api_key": key}
        if ws_id:
            kw["default_headers"] = {"anthropic-workspace-id": ws_id}
        client = anthropic.Anthropic(**kw)
        resp = client.messages.create(
            model=model, max_tokens=8,
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        )
        txt = "".join(getattr(b, "text", "") for b in resp.content).strip().lower()
        return _result("anthropic", CONNECTED,
                       detail=f"model={model} reply={txt[:16]!r} "
                              f"in={resp.usage.input_tokens} out={resp.usage.output_tokens}",
                       extra={"model": model, "model_valid": True,
                              "probe_input_tokens": resp.usage.input_tokens,
                              "probe_output_tokens": resp.usage.output_tokens},
                       workspace_id=workspace_id)
    except Exception as e:  # noqa: BLE001
        status, code = _classify_anthropic(e)
        return _result("anthropic", status, detail=str(e)[:200], code=code,
                       workspace_id=workspace_id)


def _classify_anthropic(e: Exception) -> tuple[str, str]:
    name = type(e).__name__.lower()
    low = str(e).lower()
    if "workspace-id is required" in low or "anthropic-workspace-id" in low:
        return NEEDS_WORKSPACE_ID, "ANTHROPIC_NEEDS_WORKSPACE_ID"
    if ("authentication" in name or "permission" in name or "401" in low
            or "invalid x-api-key" in low or "invalid_api_key" in low):
        return AUTH_FAILED, "ANTHROPIC_AUTH_FAILED"
    if "ratelimit" in name or "429" in low or "overloaded" in name:
        return RATE_LIMITED, "ANTHROPIC_RATE_LIMITED"
    if "credit" in low or "billing" in low or "payment" in low or "insufficient" in low:
        return BILLING, "ANTHROPIC_BILLING"
    if "not_found" in low or ("model" in low and "not" in low):
        return MODEL_UNAVAILABLE, "ANTHROPIC_MODEL_UNAVAILABLE"
    return ERROR, "ANTHROPIC_PROVIDER_ERROR"


# --------------------------------------------------------------------------- #
#  Tavily — 1 tiny search (max_results=1)
# --------------------------------------------------------------------------- #

def _probe_tavily(workspace_id: str | None) -> dict:
    key = cred.get_key("tavily", workspace_id=workspace_id)
    if not key:
        return _result("tavily", NOT_CONFIGURED, detail="no API key", workspace_id=workspace_id)
    if _paid_paused():
        return _result("tavily", BLOCKED, detail="GLOBAL_PAID_PROVIDER_PAUSE is active",
                       code="PAID_PAUSED", workspace_id=workspace_id)
    try:
        from tavily import TavilyClient
    except ImportError as e:  # pragma: no cover
        return _result("tavily", ERROR, detail=f"tavily sdk missing: {e}", workspace_id=workspace_id)
    try:
        client = TavilyClient(api_key=key)
        res = client.search(query="connectivity check", max_results=1, search_depth="basic")
        n = len(res.get("results", []))
        return _result("tavily", CONNECTED, detail=f"search ok ({n} result)",
                       extra={"results": n}, workspace_id=workspace_id)
    except Exception as e:  # noqa: BLE001
        low = str(e).lower()
        if "401" in low or "unauthorized" in low or "invalid api key" in low or "forbidden" in low:
            return _result("tavily", AUTH_FAILED, detail=str(e)[:200],
                           code="TAVILY_AUTH_FAILED", workspace_id=workspace_id)
        if "429" in low or "rate" in low:
            return _result("tavily", RATE_LIMITED, detail=str(e)[:200],
                           code="TAVILY_RATE_LIMITED", workspace_id=workspace_id)
        if "quota" in low or "usage limit" in low or "plan" in low:
            return _result("tavily", QUOTA, detail=str(e)[:200],
                           code="TAVILY_QUOTA", workspace_id=workspace_id)
        return _result("tavily", ERROR, detail=str(e)[:200],
                       code="TAVILY_PROVIDER_ERROR", workspace_id=workspace_id)


# --------------------------------------------------------------------------- #
#  Google AI — free GET /v1beta/models  + model-name validation (NO generation)
# --------------------------------------------------------------------------- #

def _probe_google(workspace_id: str | None) -> dict:
    s = get_settings()
    key = cred.get_key("google", workspace_id=workspace_id)
    if not key:
        return _result("google", NOT_CONFIGURED, detail="no API key", workspace_id=workspace_id)
    from app.providers.media._http import http_json

    base = s.google_api_base.rstrip("/")
    try:
        data = http_json(f"{base}/v1beta/models?key={key}&pageSize=200",
                         timeout=s.google_timeout_seconds, vendor="google")
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "provider_code", "GOOGLE_PROVIDER_ERROR")
        status = AUTH_FAILED if code == "GOOGLE_AUTH_FAILED" else (
            RATE_LIMITED if code == "GOOGLE_RATE_LIMITED" else ERROR)
        return _result("google", status, detail=str(e)[:200], code=code, workspace_id=workspace_id)

    names = {m.get("name", "").split("/")[-1] for m in (data.get("models") or [])}
    names |= {m.get("baseModelId", "") for m in (data.get("models") or [])}
    img_ok = _model_present(s.google_image_model, names)
    vid_ok = _model_present(s.google_video_model, names)
    extra = {
        "models_visible": len(names),
        "image_model": s.google_image_model,
        "video_model": s.google_video_model,
        "image_capability": "OK" if img_ok else "MODEL_NOT_LISTED",
        "video_capability": "OK" if vid_ok else "MODEL_NOT_LISTED",
    }
    return _result("google", CONNECTED,
                   detail=f"{len(names)} models visible; image={extra['image_capability']} "
                          f"video={extra['video_capability']}",
                   extra=extra, workspace_id=workspace_id)


def _model_present(model: str, names: set[str]) -> bool:
    if not model:
        return False
    m = model.split("/")[-1]
    if m in names:
        return True
    # Imagen/Veo are often gated & not returned by ListModels even on a valid key;
    # accept a family-prefix match so we don't false-flag a working key.
    fam = m.rsplit("-", 1)[0]
    return any(n.startswith(fam) for n in names if n)


# --------------------------------------------------------------------------- #
#  ElevenLabs — free GET /v1/voices  (+ subscription)  — NO synthesis
# --------------------------------------------------------------------------- #

def _probe_elevenlabs(workspace_id: str | None) -> dict:
    s = get_settings()
    key = cred.get_key("elevenlabs", workspace_id=workspace_id)
    if not key:
        return _result("elevenlabs", NOT_CONFIGURED, detail="no API key", workspace_id=workspace_id)
    if not key.startswith("sk_"):
        return _result(
            "elevenlabs", AUTH_FAILED,
            detail="API Key ID가 아닌 sk_로 시작하는 Secret API Key가 필요합니다.",
            code="ELEVENLABS_INVALID_KEY_FORMAT", workspace_id=workspace_id,
        )
    from app.providers.media._http import http_json

    base = s.elevenlabs_api_base.rstrip("/")
    try:
        data = http_json(f"{base}/v1/voices", headers={"xi-api-key": key},
                         timeout=s.elevenlabs_timeout_seconds, vendor="elevenlabs")
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "provider_code", "ELEVENLABS_PROVIDER_ERROR")
        low = str(e).lower()
        if "missing the permission" in low or "voices_read" in low:
            return _result(
                "elevenlabs", PERMISSION_REQUIRED,
                detail="ElevenLabs API 키에 Voices: Read(voices_read) 권한이 필요합니다.",
                code="ELEVENLABS_PERMISSION_REQUIRED",
                extra={"required_permissions": ["voices_read", "text_to_speech"]},
                workspace_id=workspace_id,
            )
        if ("invalid_api_key" in low or "authentication_error" in low
                or "api key id used as api key" in low or code == "ELEVENLABS_AUTH_FAILED"):
            status, code = AUTH_FAILED, "ELEVENLABS_AUTH_FAILED"
        elif code == "ELEVENLABS_RATE_LIMITED" or "429" in low:
            status, code = RATE_LIMITED, "ELEVENLABS_RATE_LIMITED"
        elif "quota" in low or "quota_exceeded" in low:
            status, code = QUOTA, "ELEVENLABS_QUOTA"
        else:
            status = ERROR
        return _result("elevenlabs", status, detail=str(e)[:200], code=code,
                       workspace_id=workspace_id)

    voices = [
        {"voice_id": v.get("voice_id"), "name": v.get("name"),
         "labels": v.get("labels") or {}, "category": v.get("category"),
         "preview_url": v.get("preview_url")}
        for v in (data.get("voices") or [])
    ]
    saved_voice = ""
    try:
        d = cred.describe("elevenlabs", workspace_id=workspace_id)
        saved_voice = (d.get("meta") or {}).get("voice_id", "")
    except Exception:  # noqa: BLE001
        pass
    chosen = s.elevenlabs_voice_id or saved_voice
    voice_selected = bool(chosen) and any(v["voice_id"] == chosen for v in voices)
    extra = {
        "voices": voices[:60],
        "voice_count": len(voices),
        "voice_id": chosen,
        "voice_selected": voice_selected,
        "model": s.elevenlabs_model,
    }
    status = CONNECTED  # connected regardless; voice selection is a separate signal
    detail = f"{len(voices)} voices; voice_selected={voice_selected}"
    return _result("elevenlabs", status, detail=detail, extra=extra, workspace_id=workspace_id)


# --------------------------------------------------------------------------- #
#  Ollama — reuse the existing free health check (no cost, already verified)
# --------------------------------------------------------------------------- #

def _probe_ollama(workspace_id: str | None) -> dict:
    s = get_settings()
    from app.providers.ollama_llm import check_health

    h = check_health(base_url=s.ollama_base_url, model=s.ollama_default_model)
    if not s.ollama_enabled:
        return {"provider": "ollama", "status": "DISABLED", "ok": False,
                "detail": "OLLAMA_ENABLED=false"}
    if h["reachable"] and h["model_available"]:
        return {"provider": "ollama", "status": CONNECTED, "ok": True,
                "detail": f"{s.ollama_default_model} available",
                "model": s.ollama_default_model, "model_available": True}
    if h["reachable"]:
        return {"provider": "ollama", "status": "DEGRADED", "ok": False,
                "detail": f"service up but {s.ollama_default_model} not pulled"}
    return {"provider": "ollama", "status": ERROR, "ok": False,
            "detail": h.get("reason") or h.get("error") or "not reachable"}


_PROBES = {
    "anthropic": _probe_anthropic,
    "tavily": _probe_tavily,
    "google": _probe_google,
    "elevenlabs": _probe_elevenlabs,
    "ollama": _probe_ollama,
}


def run(provider: str, *, workspace_id: str | None = None) -> dict:
    fn = _PROBES.get(provider)
    if fn is None:
        raise ValueError(f"unknown provider: {provider!r}")
    return fn(workspace_id)
