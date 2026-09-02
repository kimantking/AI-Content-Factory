"""§23-§27, §83 — Cost Estimator: platform diff, OFF platform 0, no fake prices."""
from __future__ import annotations

from app.ai_router.cost import estimate_campaign_cost


def _sel(*pairs):
    return {p: {"_": m} for p, m in pairs}


def test_more_platforms_cost_more_or_equal(_base_settings):
    _base_settings.ollama_enabled = True
    yt = estimate_campaign_cost(None, selection={"youtube_shorts": "GENERATE_AND_PUBLISH"},
                                quality_preset="balanced")
    multi = estimate_campaign_cost(None, selection={
        "youtube_shorts": "GENERATE_AND_PUBLISH", "tiktok": "GENERATE_AND_PUBLISH",
        "instagram_reel": "GENERATE_AND_PUBLISH"}, quality_preset="balanced")
    assert multi["categories"]["LLM"]["detail"]["adaptation_platforms"] == 3
    assert yt["categories"]["LLM"]["detail"]["adaptation_platforms"] == 1
    # known LLM total is non-decreasing with more platforms
    assert multi["total_known_usd"] >= yt["total_known_usd"]


def test_disabled_platform_adds_no_platform_specific_cost(_base_settings):
    _base_settings.ollama_enabled = True
    a = estimate_campaign_cost(None, selection={"youtube_shorts": "GENERATE_AND_PUBLISH"})
    b = estimate_campaign_cost(None, selection={
        "youtube_shorts": "GENERATE_AND_PUBLISH", "tiktok": "DISABLED", "instagram_reel": "DISABLED"})
    assert a["categories"]["LLM"]["detail"]["adaptation_platforms"] == \
        b["categories"]["LLM"]["detail"]["adaptation_platforms"] == 1
    assert set(b["generate_platforms"]) == {"youtube_shorts"}


def test_media_cost_is_unknown_not_fabricated(_base_settings):
    _base_settings.ollama_enabled = True
    r = estimate_campaign_cost(None, selection={"youtube_shorts": "GENERATE_AND_PUBLISH"},
                               quality_preset="high")
    for cat in ("Image", "Video", "TTS"):
        assert r["categories"][cat]["state"] == "UNKNOWN"
        assert r["categories"][cat]["usd"] is None
    assert r["has_unknown"] is True and r["total_state"] == "UNKNOWN"


def test_local_processing_is_labelled_not_free(_base_settings):
    _base_settings.ollama_enabled = True
    _base_settings.allow_cloud_fallback = False   # force local
    r = estimate_campaign_cost(None, selection={"youtube_shorts": "GENERATE_ONLY"},
                               quality_preset="fast")
    assert r["categories"]["LLM"]["local_processing"] is True
    assert "로컬" in r["note"] and "자원" in r["note"]


def test_learn_only_has_no_media_or_master_llm(_base_settings):
    _base_settings.ollama_enabled = True
    r = estimate_campaign_cost(None, selection={}, execution_mode="LEARN_ONLY",
                               reference_count=30)
    assert "Image" not in r["categories"] and "Video" not in r["categories"]
    assert "LLM" not in r["categories"]                    # no master content
    assert r["categories"]["LLM_learning"]["detail"]["deep_analysed"] <= 30


def test_shared_master_media_counted_once(_base_settings):
    _base_settings.ollama_enabled = True
    r = estimate_campaign_cost(None, selection={
        "youtube_shorts": "GENERATE_AND_PUBLISH", "tiktok": "GENERATE_AND_PUBLISH"},
        quality_preset="balanced")
    assert r["categories"]["Video"]["detail"]["shared_master"] == 1
    assert r["categories"]["Video"]["detail"]["platform_variants"] == 2
