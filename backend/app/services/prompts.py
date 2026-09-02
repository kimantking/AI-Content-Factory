from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@dataclass(frozen=True)
class PromptText:
    name: str
    version: str
    body: str
    content_hash: str


@lru_cache(maxsize=64)
def load_prompt(name: str, version: str = "v1") -> PromptText:
    path = PROMPTS_DIR / name / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path}")
    body = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return PromptText(name=name, version=version, body=body, content_hash=digest)


def register_prompt(session, name: str, version: str = "v1") -> str:
    """Ensure a prompt_versions row exists for this (name, version, hash). Returns version label."""
    from app.db.models import PromptVersion

    p = load_prompt(name, version)
    exists = (
        session.query(PromptVersion)
        .filter_by(name=name, version=version, content_hash=p.content_hash)
        .first()
    )
    if not exists:
        session.add(
            PromptVersion(name=name, version=version, content_hash=p.content_hash, body=p.body)
        )
        session.flush()
    return version
