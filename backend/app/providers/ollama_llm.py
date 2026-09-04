"""Local Ollama LLM provider (Phase 8).

Talks to the Ollama REST API directly over stdlib urllib — no `ollama` python
package dependency. Implements the same `LLMProvider` protocol (`.complete`) as the
cloud adapters, plus `health()` / `list_models()` for the Model Registry and the
Local AI settings screen.

Ollama being down NEVER crashes the app: `health()` returns a status dict, and
`complete()` raises a normalized `ProviderError` the Model Router can fall back on.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from app.providers.base import LLMResponse
from app.providers.errors import InvalidOutputError, ProviderError, TimeoutError_

_APPROX_CHARS_PER_TOKEN = 4
_REACHABLE_STATUSES = frozenset({"CONNECTED", "OK", "RUNNING", "READY", "UP", "AVAILABLE"})


def _approx_tokens(text: str) -> int:
    return max(1, round(len(text or "") / _APPROX_CHARS_PER_TOKEN))


class OllamaLLMProvider:
    name = "ollama"

    def __init__(self, *, base_url: str = "http://localhost:11434",
                 model: str = "gemma3:4b", timeout_seconds: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds

    # -- low level ------------------------------------------------------- #

    def _request(self, path: str, payload: dict | None = None, *, method: str = "POST",
                 timeout: float | None = None) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:300]
            except Exception:  # noqa: BLE001
                pass
            if e.code == 404:
                raise ProviderError(f"ollama 404 (model missing?): {body}", error_type="INVALID_OUTPUT") from e
            raise ProviderError(f"ollama http {e.code}: {body}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            reason = getattr(e, "reason", e)
            if "timed out" in str(reason).lower():
                raise TimeoutError_(f"ollama timeout after {timeout or self.timeout}s") from e
            raise ProviderError(f"ollama unreachable at {self.base_url}: {reason}") from e
        try:
            return json.loads(raw.decode())
        except ValueError as e:
            raise ProviderError(f"ollama non-JSON response: {e}") from e

    # -- health / discovery ------------------------------------------- #

    def health(self) -> dict:
        """{status: CONNECTED|NOT_RUNNING|DEGRADED, models:[...], version:str}."""
        try:
            tags = self._request("/api/tags", method="GET", timeout=6)
        except ProviderError as e:
            et = getattr(e, "error_type", "PROVIDER_ERROR")
            return {"status": "NOT_RUNNING" if et != "TIMEOUT" else "DEGRADED",
                    "reason": str(e), "models": [], "version": None}
        models = [m.get("name") for m in tags.get("models", []) if m.get("name")]
        version = None
        try:
            version = self._request("/api/version", method="GET", timeout=4).get("version")
        except ProviderError:
            pass
        return {"status": "CONNECTED", "models": models, "version": version, "reason": ""}

    def list_models(self) -> list[dict]:
        tags = self._request("/api/tags", method="GET", timeout=6)
        out = []
        for m in tags.get("models", []):
            det = m.get("details", {}) or {}
            out.append({
                "model_id": m.get("name"),
                "family": (det.get("family") or "").lower(),
                "parameter_size": det.get("parameter_size", ""),
                "quantization": det.get("quantization_level", ""),
                "size_bytes": m.get("size", 0),
                "capabilities": m.get("capabilities", []),
            })
        return out

    def has_model(self, model: str | None = None) -> bool:
        want = model or self.model
        try:
            return want in {m["model_id"] for m in self.list_models()}
        except ProviderError:
            return False

    # -- inference --------------------------------------------------- #

    def complete(self, *, system: str, user: str, task: str, context: dict) -> LLMResponse:
        """Structured completion. Uses Ollama's `format:"json"` to force a JSON
        object, matching the cloud adapters' contract."""
        plain_text = bool(context.get("plain_text"))
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": float(context.get("temperature", 0.4)),
                        "num_predict": int(context.get("max_tokens", 1200))},
            "messages": [
                {"role": "system",
                 "content": (system or "") + ("" if plain_text else "\n\nRespond with a single valid JSON object only.")},
                {"role": "user", "content": user},
            ],
        }
        if not plain_text:
            payload["format"] = "json"
        started = time.monotonic()
        data = self._request("/api/chat", payload)
        elapsed = time.monotonic() - started
        text = (data.get("message", {}) or {}).get("content", "").strip()
        if plain_text:
            if not text:
                raise InvalidOutputError(f"empty ollama output for task={task}")
            # The router expects structured JSON. Chat answers are generated as
            # natural text so long scripts cannot become invalid when a model
            # stops at its token limit; the application performs the wrapping.
            text = json.dumps({"reply": text}, ensure_ascii=False)
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):] if "{" in text else text
        try:
            json.loads(text)
        except ValueError as e:
            raise InvalidOutputError(f"non-JSON ollama output for task={task}: {e}") from e
        return LLMResponse(
            text=text,
            input_tokens=int(data.get("prompt_eval_count") or _approx_tokens(system + user)),
            output_tokens=int(data.get("eval_count") or _approx_tokens(text)),
            provider=self.name,
            model=f"{self.model}@{round(elapsed, 2)}s",
        )

    def ping_inference(self) -> dict:
        """Tiny end-to-end check for the settings screen / benchmark."""
        try:
            r = self.complete(system="You are a test.", user='Return {"ok": true}',
                              task="ping", context={"max_tokens": 32})
            return {"ok": True, "sample": r.text[:120], "model": self.model}
        except ProviderError as e:
            return {"ok": False, "error": str(e), "error_type": getattr(e, "error_type", "PROVIDER_ERROR")}


def check_health(*, base_url: str, model: str, timeout_seconds: int = 120) -> dict:
    """Run one Ollama health request and add the shared availability signals."""
    try:
        health = OllamaLLMProvider(base_url=base_url, model=model,
                                   timeout_seconds=timeout_seconds).health()
    except Exception as e:  # noqa: BLE001 — health checks never crash callers
        health = {"status": "NOT_RUNNING", "models": [], "reason": str(e)}
    models = health.get("models") or []
    return {
        **health,
        "reachable": health.get("status") in _REACHABLE_STATUSES,
        "model_available": model in models,
    }
