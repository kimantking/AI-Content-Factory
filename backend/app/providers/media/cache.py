from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from app.config import get_settings


def asset_hash(*, provider: str, model: str, prompt: str, settings: dict,
               aspect_ratio: str) -> str:
    blob = json.dumps(
        {"provider": provider, "model": model, "prompt": prompt,
         "settings": settings, "aspect_ratio": aspect_ratio},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class AssetCache:
    """Content-addressed cache so repeated dev/test generations don't re-hit a
    paid API. Callers that need per-platform originality must pass allow_cache=False.
    """

    def __init__(self, root: str | None = None):
        s = get_settings()
        self.enabled = s.asset_cache_enabled
        self.dir = Path(s.storage_root).resolve() / "_cache"
        self.dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, dest: str) -> bool:
        if not self.enabled:
            return False
        for f in self.dir.glob(key + ".*"):
            shutil.copyfile(f, dest)
            return True
        return False

    def put(self, key: str, src: str) -> None:
        if not self.enabled:
            return
        ext = Path(src).suffix or ".bin"
        try:
            shutil.copyfile(src, self.dir / f"{key}{ext}")
        except OSError:
            pass
