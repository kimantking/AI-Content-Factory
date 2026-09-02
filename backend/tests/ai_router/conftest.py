from __future__ import annotations

import json

import pytest

from app.ai_router.registry import ModelEntry, ModelRegistry
from app.providers.base import LLMResponse


@pytest.fixture
def full_registry():
    """A registry with local + cheap-cloud + premium-cloud all enabled and OK,
    so router-logic tests don't depend on a live Ollama or a cloud key."""
    return ModelRegistry([
        ModelEntry("python", "python", "deterministic", "deterministic", enabled=True,
                   health="OK", context_tokens=0, latency_class="instant", quality_class="basic"),
        ModelEntry("gemma3:4b", "ollama", "gemma3", "local", enabled=True, health="OK",
                   context_tokens=8192, latency_class="medium", quality_class="standard"),
        ModelEntry("claude-haiku-4-5-20251001", "anthropic", "claude", "cloud", enabled=True,
                   health="OK", context_tokens=200_000, latency_class="fast",
                   quality_class="standard", vision=True, tools=True),
        ModelEntry("claude-sonnet-5", "anthropic", "claude", "cloud", enabled=True, health="OK",
                   context_tokens=200_000, latency_class="medium", quality_class="premium",
                   vision=True, tools=True),
    ])


class RecordingProvider:
    """Fake LLM provider that records calls and returns a fixed JSON object."""

    def __init__(self, name, model, *, payload=None, raise_error=None, bad_json=False,
                 low_confidence=False):
        self.name = name
        self.model = model
        self.calls: list[dict] = []
        self._payload = payload or {"ok": True}
        self._raise = raise_error
        self._bad_json = bad_json
        self._low_conf = low_confidence

    def complete(self, *, system, user, task, context):
        self.calls.append({"task": task, "system": system[:40], "user": user[:40]})
        if self._raise:
            raise self._raise
        if self._bad_json:
            text = "not json at all"
        elif self._low_conf:
            text = json.dumps({**self._payload, "confidence": 0.1})
        else:
            text = json.dumps(self._payload)
        return LLMResponse(text=text, input_tokens=100, output_tokens=50,
                           provider=self.name, model=self.model)
