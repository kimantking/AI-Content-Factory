"""Google AI (Imagen) image adapter — stdlib HTTP, no new dependency.

Implements the existing `ImageProvider` protocol. Model name comes from
`settings.google_image_model` (one place). If Google is not configured this
raises `GOOGLE_NOT_CONFIGURED`; the registry only selects this adapter when a key
is present, so in practice it always has one.
"""
from __future__ import annotations

import base64

from app.config import get_settings
from app.providers.media._http import http_json, provider_error
from app.providers.media.base import MediaResult
from app.schemas.media import ProviderMode

# Imagen 3/4 were retired. Keep old .env values working by translating them
# to Google's current native image model and endpoint.
_CURRENT_IMAGE_MODEL = "gemini-3.1-flash-image"

# Native Gemini image generation supports these aspect ratios.
_RATIOS = {(1, 1): "1:1", (9, 16): "9:16", (16, 9): "16:9", (3, 4): "3:4", (4, 3): "4:3"}


def _effective_model(configured: str) -> str:
    return _CURRENT_IMAGE_MODEL if configured.startswith("imagen-") else configured


def _image_part(data: dict) -> tuple[bytes, str]:
    candidates = data.get("candidates") or []
    parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
    for part in parts:
        inline = part.get("inlineData") or part.get("inline_data") or {}
        encoded = inline.get("data")
        if encoded:
            return base64.b64decode(encoded), inline.get("mimeType") or inline.get("mime_type") or "image/png"
    raise provider_error("google", "PROVIDER_ERROR", "no image in response")


def _aspect(width: int, height: int) -> str:
    if height <= 0:
        return "1:1"
    target = width / height
    best, bd = "1:1", 1e9
    for (w, h), label in _RATIOS.items():
        d = abs((w / h) - target)
        if d < bd:
            best, bd = label, d
    return best


class GoogleImageProvider:
    name = "google-imagen"
    mode = ProviderMode.REAL

    def __init__(self) -> None:
        s = get_settings()
        self._key = s.google_api_key or s.image_api_key
        self._base = s.google_api_base.rstrip("/")
        self._configured_model = s.google_image_model
        self._model = _effective_model(self._configured_model)
        self._timeout = s.google_timeout_seconds
        if not self._key:
            raise provider_error("google", "NOT_CONFIGURED", "GOOGLE_API_KEY is not set")

    def generate_image(self, *, prompt: str, negative_prompt: str, width: int, height: int,
                       out_path: str, seed: int | None = None) -> MediaResult:
        url = f"{self._base}/v1beta/models/{self._model}:generateContent?key={self._key}"
        full_prompt = prompt
        if negative_prompt:
            full_prompt += f"\nAvoid: {negative_prompt}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": _aspect(width, height)},
            },
        }

        data = http_json(url, method="POST", body=payload, timeout=self._timeout, vendor="google")
        img_bytes, mime = _image_part(data)
        with open(out_path, "wb") as f:
            f.write(img_bytes)

        return MediaResult(
            path=out_path, mime_type=mime, provider=self.name, provider_mode=self.mode,
            width=width, height=height,
            cost=0.0,   # Google image pricing is UNKNOWN until verified — never fabricated
            meta={"model": self._model, "configured_model": self._configured_model,
                  "aspect_ratio": _aspect(width, height),
                  "cost_state": "UNKNOWN", "prompt": prompt[:400],
                  "negative_prompt": negative_prompt[:200], "bytes": len(img_bytes)},
        )

    # ---- read-only connection test (no generation, no cost) ---- #
    def health(self) -> dict:
        try:
            data = http_json(f"{self._base}/v1beta/models?key={self._key}",
                             timeout=self._timeout, vendor="google")
            n = len(data.get("models") or [])
            return {"status": "CONNECTED", "models_visible": n, "image_model": self._model}
        except Exception as e:  # noqa: BLE001
            return {"status": "ERROR", "provider_code": getattr(e, "provider_code", "GOOGLE_PROVIDER_ERROR"),
                    "detail": str(e)[:200]}
