"""Resolve media credentials per campaign without mutating process settings."""
from contextlib import contextmanager
from contextvars import ContextVar

from app.providers import credentials

_workspace = ContextVar("media_workspace", default=None)


@contextmanager
def media_workspace(workspace_id):
    token = _workspace.set(workspace_id)
    try:
        yield
    finally:
        _workspace.reset(token)


def key(provider, fallback=None):
    return credentials.get_key(provider, workspace_id=_workspace.get()) or fallback


def voice():
    from app.config import get_settings

    meta = credentials.describe("elevenlabs", workspace_id=_workspace.get()).get("meta") or {}
    return str(meta.get("voice_id") or get_settings().elevenlabs_voice_id or "").strip()
