"""§2, §14-§16, §79 — Ollama provider. Real local verification when reachable,
otherwise the provider still degrades gracefully (no crash)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from app.providers.errors import ProviderError
from app.providers.ollama_llm import OllamaLLMProvider

_OLLAMA = "http://localhost:11434"


def _ollama_up() -> bool:
    try:
        urllib.request.urlopen(_OLLAMA + "/api/tags", timeout=3).read()
        return True
    except Exception:  # noqa: BLE001
        return False


ollama_available = pytest.mark.skipif(not _ollama_up(), reason="Ollama not reachable")


def test_health_never_raises_when_down():
    p = OllamaLLMProvider(base_url="http://127.0.0.1:59999", model="gemma3:4b", timeout_seconds=2)
    h = p.health()
    assert h["status"] in ("NOT_RUNNING", "DEGRADED")
    assert h["models"] == [] and "reason" in h


def test_complete_raises_normalized_error_when_down():
    p = OllamaLLMProvider(base_url="http://127.0.0.1:59999", model="gemma3:4b", timeout_seconds=2)
    with pytest.raises(ProviderError):
        p.complete(system="s", user="u", task="t", context={})


@ollama_available
def test_health_lists_models_locally():
    p = OllamaLLMProvider(base_url=_OLLAMA)
    h = p.health()
    assert h["status"] == "CONNECTED"
    assert isinstance(h["models"], list)


@ollama_available
def test_gemma3_4b_present_and_infers():
    p = OllamaLLMProvider(base_url=_OLLAMA, model="gemma3:4b", timeout_seconds=90)
    if not p.has_model("gemma3:4b"):
        pytest.skip("gemma3:4b not pulled on this machine")
    r = p.complete(system="You are a classifier. Return JSON.",
                   user='Classify: "The central bank raised rates." Return {"label": "NEWS"|"OTHER"}.',
                   task="classification", context={"max_tokens": 40})
    data = json.loads(r.text)
    assert isinstance(data, dict) and "label" in data
    assert r.provider == "ollama" and r.output_tokens > 0
