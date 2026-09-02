from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import session_scope
from app.db.models import Campaign, PlatformAccount
from app.publishing.capabilities import get_capability
from app.publishing.crypto import encrypt_token
from app.publishing.mock_platform import mock_platform


@pytest.fixture(autouse=True)
def _reset_mock_platform():
    mock_platform.reset()
    yield
    mock_platform.reset()


@pytest.fixture(autouse=True)
def _publishing_defaults(_base_settings):
    _base_settings.platform_client = "mock"
    _base_settings.dry_run = False
    _base_settings.publish_mode = "MANUAL"
    _base_settings.run_inline = True
    yield


def _connect(platform: str, account_type: str = "BUSINESS") -> str:
    cap = get_capability(platform)
    cid = str(uuid.uuid4())
    with session_scope() as s:
        s.add(PlatformAccount(
            id=cid, platform=platform, account_id=f"mock-{platform}",
            account_name=f"Mock {platform}", account_type=account_type,
            scopes=list(cap.required_scopes),
            access_token_encrypted=encrypt_token(f"mock-access-{platform}"),
            refresh_token_encrypted=encrypt_token(f"mock-refresh-{platform}"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            connection_status="CONNECTED", integration_status="MOCK_TESTED",
        ))
    return cid


@pytest.fixture
def connect_account():
    return _connect


@pytest.fixture
def ready_media_campaign(_base_settings, tmp_path):
    """Phase 1-A + media pipeline complete -> PlatformContent + assets exist."""
    _base_settings.storage_root = str(tmp_path / "storage")
    _base_settings.output_root = str(tmp_path / "outputs")
    _base_settings.asset_cache_enabled = False
    from app.providers.media import registry as mr

    mr.get_storage.cache_clear()

    from app.agents.media_runner import run_media_pipeline
    from app.agents.runner import run_pipeline

    cid = str(uuid.uuid4())
    topic = "AI로 사라질 가능성이 높은 직업"
    platforms = ["youtube_shorts", "instagram_carousel", "threads", "naver_clip"]
    with session_scope() as s:
        s.add(Campaign(id=cid, topic=topic, audience_goal="VIEWS",
                       platforms=platforms, status="WAITING"))
    run_pipeline(cid, topic, "VIEWS", platforms)
    run_media_pipeline(cid, platforms)
    mr.get_storage.cache_clear()
    return cid
