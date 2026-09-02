from __future__ import annotations

import uuid

import pytest

from app.agents.runner import run_pipeline
from app.db.base import session_scope
from app.db.models import Campaign

TOPIC = "AI로 사라질 가능성이 높은 직업"


@pytest.fixture
def tmp_storage(tmp_path, _base_settings):
    _base_settings.storage_root = str(tmp_path / "storage")
    _base_settings.output_root = str(tmp_path / "outputs")
    _base_settings.asset_cache_enabled = False
    from app.providers.media import registry as media_registry

    media_registry.get_storage.cache_clear()
    yield tmp_path
    media_registry.get_storage.cache_clear()


@pytest.fixture
def ready_campaign(_base_settings, tmp_storage):
    cid = str(uuid.uuid4())
    platforms = ["youtube_shorts"]
    with session_scope() as s:
        s.add(Campaign(id=cid, topic=TOPIC, audience_goal="VIEWS",
                       platforms=platforms, status="WAITING"))
    run_pipeline(cid, TOPIC, "VIEWS", platforms)
    with session_scope() as s:
        assert s.get(Campaign, cid).status == "SUCCESS"
    return cid
