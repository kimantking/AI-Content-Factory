from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from app.config import get_settings


class SecretManager(Protocol):
    name: str

    def get_secret(self, key: str) -> str | None: ...
    def has_secret(self, key: str) -> bool: ...
    def rotate_reference(self, key: str) -> str: ...
    def health_check(self) -> dict: ...


class EnvSecretManager:
    name = "env"

    def get_secret(self, key: str) -> str | None:
        return os.environ.get(key.upper()) or getattr(get_settings(), key.lower(), None)

    def has_secret(self, key: str) -> bool:
        return self.get_secret(key) not in (None, "")

    def rotate_reference(self, key: str) -> str:
        return f"env:{key.upper()}"

    def health_check(self) -> dict:
        return {"provider": self.name, "status": "OK"}


class DockerSecretManager:
    """Reads /run/secrets/<key> (Docker/Swarm secrets), falling back to env."""

    name = "docker"

    def __init__(self, base: str = "/run/secrets"):
        self.base = Path(base)
        self._env = EnvSecretManager()

    def get_secret(self, key: str) -> str | None:
        p = self.base / key.lower()
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8").strip()
            except OSError:
                pass
        return self._env.get_secret(key)

    def has_secret(self, key: str) -> bool:
        return self.get_secret(key) not in (None, "")

    def rotate_reference(self, key: str) -> str:
        return f"docker-secret:{key.lower()}"

    def health_check(self) -> dict:
        return {"provider": self.name, "status": "OK" if self.base.exists() else "NO_SECRETS_DIR"}


def get_secret_manager() -> SecretManager:
    if Path("/run/secrets").exists():
        return DockerSecretManager()
    return EnvSecretManager()
