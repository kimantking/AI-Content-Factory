from __future__ import annotations

import pytest

from app.agents.media_runner import run_media_pipeline
from app.db.base import session_scope
from app.db.models import Asset, Scene
from app.providers.errors import ProviderError
from app.providers.faults import faults
from app.services.budget import BudgetExceeded

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _pg_checkpointer(_base_settings):
    # resume across separate pipeline invocations needs the durable checkpointer
    _base_settings.checkpointer_kind = "postgres"
    yield


def test_tts_failure_then_resume_keeps_images(ready_campaign):
    cid = ready_campaign
    faults.arm("tts", error_type="AUTH_ERROR", times=99)   # non-retryable => hard stop at gen_voice
    with pytest.raises(ProviderError):
        run_media_pipeline(cid, ["youtube_shorts"])

    with session_scope() as s:
        img_ids = {a.id for a in s.query(Asset).filter_by(campaign_id=cid, asset_type="image")}
        assert img_ids                                       # images were generated before the failure
        assert s.query(Asset).filter_by(campaign_id=cid, asset_type="audio").count() == 0

    faults.clear()
    state = run_media_pipeline(cid, ["youtube_shorts"], resume=True)
    assert state["status"] in ("SUCCESS", "FIX_REQUIRED")

    with session_scope() as s:
        img_ids_after = {a.id for a in s.query(Asset).filter_by(campaign_id=cid, asset_type="image")}
        assert img_ids_after == img_ids                      # NOT regenerated on resume
        assert s.query(Asset).filter_by(campaign_id=cid, asset_type="render").count() == 1


def test_media_budget_guard_blocks_then_allows(ready_campaign, _base_settings):
    cid = ready_campaign
    _base_settings.media_budget_usd = 0.0
    _base_settings.image_provider = "stubcost"  # force a non-zero cost via monkeypatched provider

    # give the mock image provider a cost so the budget guard actually trips
    import app.agents.media_nodes as mn
    from app.providers.media.mock_image import MockImageProvider

    class Costly(MockImageProvider):
        def generate_image(self, **kw):
            r = super().generate_image(**kw)
            r.cost = 0.5
            return r

    orig = mn.get_image_provider
    mn.get_image_provider = lambda: Costly()
    try:
        with pytest.raises(BudgetExceeded):
            run_media_pipeline(cid, ["youtube_shorts"])
        with session_scope() as s:
            assert s.query(Scene).filter_by(campaign_id=cid).count() >= 3   # scenes survived
        _base_settings.media_budget_usd = 50.0
        mn.get_image_provider = orig                                        # cost-free again
        state = run_media_pipeline(cid, ["youtube_shorts"], resume=True)
        assert state["status"] in ("SUCCESS", "FIX_REQUIRED")
    finally:
        mn.get_image_provider = orig
