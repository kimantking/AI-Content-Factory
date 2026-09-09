"""Google AI (Veo) video adapter — stdlib HTTP, no new dependency.

Implements the existing `VideoProvider` protocol. Veo generation is a
long-running operation: submit -> poll operation -> retrieve. `generate_video`
drives that loop synchronously inside the worker job (bounded by
`google_video_max_wait_seconds`), so the existing Job / checkpointer /
idempotency architecture is untouched — the media node's `_existing_scene_asset`
reuse still prevents re-generation on a worker restart.

Model name comes from `settings.google_video_model` (one place).
No paid video call is made by any test.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings
from app.providers.media import runtime
from app.providers.media._http import http_bytes, http_json, provider_error
from app.providers.media.base import MediaResult
from app.schemas.media import ProviderMode


class GoogleVideoProvider:
    name = "google-veo"
    mode = ProviderMode.REAL

    def __init__(self) -> None:
        s = get_settings()
        self._key = runtime.key("google", s.video_api_key)
        self._base = s.google_api_base.rstrip("/")
        self._model = s.google_video_model.removeprefix("models/")
        self._timeout = s.google_timeout_seconds
        self._max_wait = int(getattr(s, "google_video_max_wait_seconds", 600))
        self._poll = int(getattr(s, "google_video_poll_seconds", 10))
        if not self._key:
            raise provider_error("google", "NOT_CONFIGURED", "GOOGLE_API_KEY is not set")

    def generate_video(self, *, prompt: str, reference_image: str | None, duration: float,
                       width: int, height: int, camera_motion: str, out_path: str) -> MediaResult:
        submit = f"{self._base}/v1beta/models/{self._model}:predictLongRunning?key={self._key}"
        instance: dict = {"prompt": prompt}
        if reference_image:
            try:
                with open(reference_image, "rb") as f:
                    instance["image"] = {"bytesBase64Encoded": base64.b64encode(f.read()).decode(),
                                         "mimeType": "image/png"}
            except OSError:
                pass
        params = {"aspectRatio": "16:9" if width >= height else "9:16"}
        # Scene timing is normalized by our renderer. Veo 3 clips use supported
        # eight-second generation rather than arbitrary narration durations.
        params["durationSeconds"] = 8
        payload = {"instances": [instance], "parameters": params}
        fingerprint = hashlib.sha256(json.dumps({"model": self._model, "payload": payload},
                                                sort_keys=True).encode()).hexdigest()
        checkpoint = Path(out_path + ".operation.json")
        saved = json.loads(checkpoint.read_text()) if checkpoint.is_file() else {}
        op_name = saved.get("name") if saved.get("fingerprint") == fingerprint else None
        if not op_name:
            op = http_json(submit, method="POST", body=payload,
                           timeout=self._timeout, vendor="google")
            op_name = op.get("name")
            if op_name:
                temporary = checkpoint.with_suffix(".tmp")
                temporary.write_text(json.dumps({"name": op_name, "fingerprint": fingerprint}))
                temporary.replace(checkpoint)
        if not op_name:
            raise provider_error("google", "PROVIDER_ERROR", "no operation name from predictLongRunning")

        # ---- poll (bounded) ----
        deadline = time.monotonic() + self._max_wait
        result = None
        while time.monotonic() < deadline:
            st = http_json(f"{self._base}/v1beta/{op_name}?key={self._key}",
                           timeout=self._timeout, vendor="google")
            if st.get("error"):
                raise provider_error("google", "PROVIDER_ERROR",
                                     str(st["error"].get("message", "operation failed")))
            if st.get("done"):
                result = st.get("response") or {}
                break
            time.sleep(self._poll)
        if result is None:
            raise provider_error("google", "TIMEOUT",
                                 f"Veo operation not done after {self._max_wait}s")

        vid_bytes = self._extract_video(result)
        with open(out_path, "wb") as f:
            f.write(vid_bytes)
        return MediaResult(
            path=out_path, mime_type="video/mp4", provider=self.name, provider_mode=self.mode,
            width=width, height=height, duration=duration, cost=0.0,
            meta={"model": self._model, "operation": op_name, "cost_state": "UNKNOWN",
                  "bytes": len(vid_bytes), "prompt": prompt[:400]},
        )

    def _extract_video(self, response: dict) -> bytes:
        preds = ((response.get("generateVideoResponse") or {}).get("generatedSamples")
                 or response.get("predictions") or response.get("generatedVideos") or [])
        for p in preds if isinstance(preds, list) else [preds]:
            if isinstance(p, dict):
                if p.get("bytesBase64Encoded"):
                    return base64.b64decode(p["bytesBase64Encoded"])
                uri = p.get("video", {}).get("uri") or p.get("uri") or p.get("fileUri")
                if uri:
                    parsed = urlparse(uri)
                    if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".googleapis.com"):
                        raise provider_error("google", "PROVIDER_ERROR", "untrusted video download host")
                    return http_bytes(uri, method="GET", headers={"x-goog-api-key": self._key},
                                      timeout=self._timeout, vendor="google")
        raise provider_error("google", "PROVIDER_ERROR", "no video payload in operation response")

    def health(self) -> dict:
        try:
            data = http_json(f"{self._base}/v1beta/models?key={self._key}",
                             timeout=self._timeout, vendor="google")
            return {"status": "CONNECTED", "models_visible": len(data.get("models") or []),
                    "video_model": self._model}
        except Exception as e:  # noqa: BLE001
            return {"status": "ERROR",
                    "provider_code": getattr(e, "provider_code", "GOOGLE_PROVIDER_ERROR"),
                    "detail": str(e)[:200]}
