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

# Imagen supports a fixed set of aspect ratios.
_RATIOS = {(1, 1): "1:1", (9, 16): "9:16", (16, 9): "16:9", (3, 4): "3:4", (4, 3): "4:3"}


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
        self._model = s.google_image_model
        self._timeout = s.google_timeout_seconds
        if not self._key:
            raise provider_error("google", "NOT_CONFIGURED", "GOOGLE_API_KEY is not set")

    def generate_image(self, *, prompt: str, negative_prompt: str, width: int, height: int,
                       out_path: str, seed: int | None = None) -> MediaResult:
        url = f"{self._base}/v1beta/models/{self._model}:predict?key={self._key}"
        params: dict = {"sampleCount": 1, "aspectRatio": _aspect(width, height)}
        if seed is not None:
            params["seed"] = int(seed)
        payload = {"instances": [{"prompt": prompt}], "parameters": params}
        if negative_prompt:
            payload["instances"][0]["negativePrompt"] = negative_prompt

        data = http_json(url, method="POST", body=payload, timeout=self._timeout, vendor="google")
        preds = data.get("predictions") or []
        if not preds or not preds[0].get("bytesBase64Encoded"):
            raise provider_error("google", "PROVIDER_ERROR", "no image in response")
        img_bytes = base64.b64decode(preds[0]["bytesBase64Encoded"])
        mime = preds[0].get("mimeType", "image/png")
        with open(out_path, "wb") as f:
            f.write(img_bytes)

        return MediaResult(
            path=out_path, mime_type=mime, provider=self.name, provider_mode=self.mode,
            width=width, height=height,
            cost=0.0,   # Google image pricing is UNKNOWN until verified — never fabricated
            meta={"model": self._model, "aspect_ratio": params["aspectRatio"],
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
