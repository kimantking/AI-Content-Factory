"""Phase 11 — AI 연결 (provider credentials + safe connection probes).

Secrets in:  PUT /api/providers/{provider}/key   { "api_key": "..." }
Secrets out: never. Responses carry last4 + status + health metadata only.

The probe (`POST .../test`) is the only real cloud call outside the pipeline.
It does not touch MOCK_MODE; the content pipeline stays mocked.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Header, HTTPException

from app.auth.context import AuthContext
from app.auth.deps import optional_auth
from app.config import get_settings
from app.db.models_p11 import KEYED_PROVIDERS
from app.providers import credentials as cred
from app.providers import probe as probe_mod

router = APIRouter(prefix="/api/providers", tags=["providers"])

_ALL = (*KEYED_PROVIDERS, "ollama")


def _ws(ctx: AuthContext | None, x_workspace_id: str | None) -> str:
    """Resolve the credential scope. Header wins; else the caller's sole
    workspace; else "" (instance-level, single-tenant / dev)."""
    if x_workspace_id:
        if ctx and not ctx.is_system_admin and x_workspace_id not in ctx.memberships:
            raise HTTPException(403, "not a member of that workspace")
        return x_workspace_id
    if ctx and len(ctx.memberships) == 1:
        return next(iter(ctx.memberships))
    return ""


def _guard(ctx: AuthContext | None) -> None:
    """Writes require workspace.manage when auth is enforced; open in dev."""
    s = get_settings()
    if s.app_env in ("production", "staging") or getattr(s, "auth_enforce", False):
        if ctx is None:
            raise HTTPException(401, "authentication required")
        if not (ctx.is_system_admin or ctx.can("workspace.manage")):
            raise HTTPException(403, "workspace.manage required")


def _check_provider(provider: str, *, keyed_only: bool = False) -> None:
    pool = KEYED_PROVIDERS if keyed_only else _ALL
    if provider not in pool:
        raise HTTPException(404, f"unknown provider: {provider}")


@router.get("")
def list_providers(probe: bool = False,
                   ctx: AuthContext | None = Depends(optional_auth),
                   x_workspace_id: str | None = Header(default=None)):
    """Per-provider connection state for the dashboard. `probe=true` also runs
    the free read-only checks (never a paid call)."""
    ws = _ws(ctx, x_workspace_id)
    out = []
    for p in KEYED_PROVIDERS:
        d = cred.describe(p, workspace_id=ws)
        if probe and p in ("google", "elevenlabs") and d["configured"]:
            try:
                probe_mod.run(p, workspace_id=ws)
                d = cred.describe(p, workspace_id=ws)
            except Exception:  # noqa: BLE001
                pass
        out.append(d)
    out.append(probe_mod.run("ollama", workspace_id=ws) if probe else _ollama_brief())
    return {"providers": out, "workspace_scope": ws or "instance"}


def _ollama_brief() -> dict:
    s = get_settings()
    return {"provider": "ollama", "status": "CONFIGURED" if s.ollama_enabled else "NOT_CONFIGURED",
            "enabled": s.ollama_enabled, "default_model": s.ollama_default_model}


@router.put("/{provider}/key")
def set_provider_key(provider: str,
                     api_key: str = Body(..., embed=True, min_length=8),
                     ctx: AuthContext | None = Depends(optional_auth),
                     x_workspace_id: str | None = Header(default=None)):
    _check_provider(provider, keyed_only=True)
    _guard(ctx)
    ws = _ws(ctx, x_workspace_id)
    actor = (ctx.email if ctx else None) or "user"
    try:
        return cred.set_key(provider, api_key, workspace_id=ws, actor=actor)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.delete("/{provider}/key")
def delete_provider_key(provider: str,
                        ctx: AuthContext | None = Depends(optional_auth),
                        x_workspace_id: str | None = Header(default=None)):
    _check_provider(provider, keyed_only=True)
    _guard(ctx)
    ws = _ws(ctx, x_workspace_id)
    actor = (ctx.email if ctx else None) or "user"
    return cred.delete_key(provider, workspace_id=ws, actor=actor)


@router.post("/{provider}/test")
def test_provider(provider: str,
                  ctx: AuthContext | None = Depends(optional_auth),
                  x_workspace_id: str | None = Header(default=None)):
    """Run ONE minimal safe live probe. No generation. No MOCK_MODE change."""
    _check_provider(provider)
    _guard(ctx)
    ws = _ws(ctx, x_workspace_id)
    try:
        return probe_mod.run(provider, workspace_id=ws)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None


@router.get("/elevenlabs/voices")
def elevenlabs_voices(ctx: AuthContext | None = Depends(optional_auth),
                      x_workspace_id: str | None = Header(default=None)):
    """Voice list from the last successful probe (cached in credential meta)."""
    ws = _ws(ctx, x_workspace_id)
    d = cred.describe("elevenlabs", workspace_id=ws)
    meta = d.get("meta") or {}
    return {"voices": meta.get("voices", []), "voice_id": meta.get("voice_id", ""),
            "voice_selected": bool(meta.get("voice_selected"))}


@router.put("/elevenlabs/voice")
def set_elevenlabs_voice(voice_id: str = Body(..., embed=True),
                         ctx: AuthContext | None = Depends(optional_auth),
                         x_workspace_id: str | None = Header(default=None)):
    _guard(ctx)
    ws = _ws(ctx, x_workspace_id)
    d = cred.describe("elevenlabs", workspace_id=ws)
    voices = (d.get("meta") or {}).get("voices", [])
    present = any(v.get("voice_id") == voice_id for v in voices)
    patch = {"voice_id": voice_id, "voice_selected": present}
    saved = cred.set_meta("elevenlabs", patch, workspace_id=ws,
                          actor=(ctx.email if ctx else None) or "user")
    # keep the running process consistent for this session
    try:
        get_settings().elevenlabs_voice_id = voice_id
    except Exception:  # noqa: BLE001
        pass
    return {**saved, "voice_present_in_account": present}
