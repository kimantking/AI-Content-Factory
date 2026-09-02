from __future__ import annotations

from typing import Protocol

from app.config import get_settings
from app.publishing.base import PublishError, PublishErrorType
from app.publishing.mock_platform import mock_platform


class PublisherClient(Protocol):
    mode: str

    def start_upload(self, platform: str, total_bytes: int) -> str: ...
    def put_chunk(self, session_id: str, nbytes: int) -> dict: ...
    def create_container(self, platform: str, idempotency_key: str, payload: dict) -> str: ...
    def container_status(self, container_id: str) -> str: ...
    def publish_container(self, platform: str, container_id: str, idempotency_key: str) -> dict: ...
    def reply(self, platform: str, parent_post_id: str, idempotency_key: str) -> dict: ...
    def get_post(self, remote_post_id: str) -> dict | None: ...
    def find_by_idempotency(self, idempotency_key: str) -> dict | None: ...


class MockPublisherClient:
    """Backed by the offline MockPlatformAPI. mode='MOCK' — results are never
    reported as real API passes."""

    mode = "MOCK"

    def start_upload(self, platform, total_bytes):
        return mock_platform.start_upload(platform, total_bytes)

    def put_chunk(self, session_id, nbytes):
        return mock_platform.put_chunk(session_id, nbytes)

    def create_container(self, platform, idempotency_key, payload):
        return mock_platform.create_container(platform, idempotency_key, payload)

    def container_status(self, container_id):
        return mock_platform.container_status(container_id)

    def publish_container(self, platform, container_id, idempotency_key):
        p = mock_platform.publish_container(platform, container_id, idempotency_key)
        return {"id": p.remote_post_id, "url": p.url}

    def reply(self, platform, parent_post_id, idempotency_key):
        p = mock_platform.reply(platform, parent_post_id, idempotency_key)
        return {"id": p.remote_post_id, "url": p.url}

    def get_post(self, remote_post_id):
        return mock_platform.get_post(remote_post_id)

    def find_by_idempotency(self, idempotency_key):
        return mock_platform.find_by_idempotency(idempotency_key)


class HttpPublisherClient:
    """Real HTTP client placeholder. Every method raises until platform
    credentials + a real adapter are wired (Phase 2 ships no verified creds)."""

    mode = "REAL"

    def _die(self, *_a, **_k):
        raise PublishError(
            PublishErrorType.PERMISSION_MISSING,
            "real platform client not configured — provide credentials and a verified adapter",
        )

    start_upload = put_chunk = create_container = container_status = _die
    publish_container = reply = get_post = find_by_idempotency = _die


def get_client() -> PublisherClient:
    s = get_settings()
    if s.platform_client == "http":
        return HttpPublisherClient()
    return MockPublisherClient()
