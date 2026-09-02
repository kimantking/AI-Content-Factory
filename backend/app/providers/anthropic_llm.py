from __future__ import annotations

import json

from app.providers.base import LLMResponse
from app.providers.errors import AuthError, InvalidOutputError, ProviderError, RateLimitError


class AnthropicLLMProvider:
    """Real adapter. Only used when LLM_PROVIDER=anthropic and a key is set.

    Agents build the prompt; this adapter is the only place the anthropic SDK
    is imported. Output is expected to be JSON; non-JSON -> INVALID_OUTPUT so
    the pipeline retries.
    """

    name = "anthropic"

    def __init__(self, api_key: str, model: str, *, workspace_id: str = ""):
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as e:  # pragma: no cover - depends on install
            raise ProviderError(f"anthropic package not installed: {e}") from e
        kw: dict = {"api_key": api_key}
        if workspace_id:
            # identity-linked Console keys require the workspace header
            kw["default_headers"] = {"anthropic-workspace-id": workspace_id}
        self._client = anthropic.Anthropic(**kw)
        self.model = model

    def complete(self, *, system: str, user: str, task: str, context: dict) -> LLMResponse:
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system + "\n\nRespond with a single valid JSON object only.",
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:  # pragma: no cover - network
            name = type(e).__name__.lower()
            if "auth" in name or "permission" in name:
                raise AuthError(str(e)) from e
            if "ratelimit" in name or "overloaded" in name:
                raise RateLimitError(str(e)) from e
            raise ProviderError(str(e)) from e

        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{") :] if "{" in text else text
        try:
            json.loads(text)
        except ValueError as e:
            raise InvalidOutputError(f"non-JSON model output for task={task}: {e}") from e
        return LLMResponse(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            provider=self.name,
            model=self.model,
        )
