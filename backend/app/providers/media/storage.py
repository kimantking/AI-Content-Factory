from __future__ import annotations

import os
from pathlib import Path

from app.config import get_settings


class LocalStorage:
    """Filesystem storage adapter. Swap for an S3-compatible adapter later without
    touching call sites (they use path_for / campaign_dir / output_dir)."""

    def __init__(self, root: str | None = None, output_root: str | None = None):
        s = get_settings()
        self.root = Path(root or s.storage_root).resolve()
        self.output = Path(output_root or s.output_root).resolve()

    def _mk(self, base: Path, parts: tuple[str, ...]) -> str:
        p = base.joinpath(*[str(x) for x in parts]) if parts else base
        target_dir = p if p.suffix == "" else p.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        return str(p)

    def path_for(self, *parts: str) -> str:
        return self._mk(self.root, parts)

    def campaign_dir(self, campaign_id: str, *parts: str) -> str:
        return self._mk(self.root / "campaigns" / campaign_id, parts)

    def output_dir(self, campaign_id: str, *parts: str) -> str:
        return self._mk(self.output / campaign_id, parts)

    @staticmethod
    def exists(path: str) -> bool:
        return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0
