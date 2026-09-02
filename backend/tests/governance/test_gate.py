from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import session_scope
from app.db.models import PublishJob
from app.governance.engine import govern_campaign


def _decision(gc, **kw):
    with session_scope() as db:
        return govern_campaign(db, campaign_id=gc["campaign_id"], content_id=gc["content_id"],
                               platform="youtube_shorts", stage="pre_publish", **kw)


# ---- §120 UNKNOWN_RIGHTS asset blocks FULL_AUTO -------------------- #

def test_unknown_rights_asset_blocks_full_auto(governed_campaign):
    gc = governed_campaign
    gc["add_asset"](asset_type="image", source_type="USER_UPLOAD", user_supplied=True)
    res = _decision(gc, run_mode="FULL_AUTO")
    assert res["decision"] == "BLOCK" and res["hard_block"] is True
    assert "RIGHTS.UNKNOWN_IN_AUTO" in res["reason_codes"]
    # a human-run mode routes it to review instead of a hard block
    res2 = _decision(gc, run_mode="MANUAL")
    assert res2["decision"] in ("HUMAN_REVIEW", "BLOCK") and res2["decision"] != "ALLOW"


# ---- §121 expired license blocks -------------------------------- #

def test_expired_license_blocks(governed_campaign):
    gc = governed_campaign
    gc["add_asset"](asset_type="music", source_type="MUSIC_LIBRARY", license_type="PROVIDER_MUSIC",
                    license_reference="lic-1",
                    expiration_at=datetime.now(timezone.utc) - timedelta(days=1))
    res = _decision(gc, run_mode="FULL_AUTO")
    assert res["decision"] == "BLOCK" and "RIGHTS.EXPIRED" in res["reason_codes"]


def test_scheduled_after_expiry_blocks(governed_campaign):
    gc = governed_campaign
    gc["add_asset"](asset_type="music", source_type="MUSIC_LIBRARY", license_type="PROVIDER_MUSIC",
                    license_reference="lic-2",
                    expiration_at=datetime.now(timezone.utc) + timedelta(days=1))
    with session_scope() as db:
        job = PublishJob(campaign_id=gc["campaign_id"], content_id=gc["content_id"],
                         platform="youtube_shorts", content_type="SHORT_VIDEO", status="PENDING",
                         run_mode="FULL_AUTO", scheduled_at=datetime.now(timezone.utc) + timedelta(days=3))
        db.add(job)
        db.flush()
        from app.governance.engine import govern_pre_publish
        res = govern_pre_publish(db, job=job)
    assert res["decision"] == "BLOCK" and "RIGHTS.EXPIRED" in res["reason_codes"]


# ---- §123 watermark blocks ------------------------------------- #

def test_watermarked_asset_blocks(governed_campaign):
    gc = governed_campaign
    gc["add_asset"](asset_type="image", source_type="STOCK_LICENSED", license_type="COMMERCIAL_STOCK",
                    license_reference="r", watermark_detected=True)
    res = _decision(gc, run_mode="FULL_AUTO")
    assert res["decision"] == "BLOCK" and "RIGHTS.WATERMARK" in res["reason_codes"]


# ---- §122 attribution FIX_REQUIRED -> package -> pass ---------- #

def test_attribution_required_then_satisfied(governed_campaign):
    gc = governed_campaign
    a = gc["add_asset"](asset_type="image", source_type="STOCK_LICENSED", license_type="CC-BY",
                        license_reference="cc-1", attribution_required=True,
                        attribution_text="Photo by Jane — CC-BY")
    res = _decision(gc, run_mode="FULL_AUTO")
    assert res["decision"] in ("ALLOW_WITH_ATTRIBUTION", "FIX_REQUIRED")
    assert any("ATTRIBUTION" in c for c in res["reason_codes"])
    # build the attribution package
    from app.governance.attribution import build_attribution_package
    with session_scope() as db:
        pkg = build_attribution_package(db, campaign_id=gc["campaign_id"])
    assert pkg["description_block"] and "Jane" in pkg["description_block"]


# ---- §127 AI disclosure required -> missing blocks -> present passes ---- #

def test_ai_disclosure_required_then_satisfied(governed_campaign):
    gc = governed_campaign
    gc["add_asset"](asset_type="image", source_type="GENERATED_VIDEO", ai_generated=True,
                    model_provider="acme", model_name="v1", model_terms_reference="terms")
    res = _decision(gc, run_mode="FULL_AUTO")
    assert res["disclosure"]["decision"] == "PLATFORM_FIELD_REQUIRED"
    assert res["decision"] in ("FIX_REQUIRED", "HUMAN_REVIEW")
    # set the platform AI field via repair
    from app.governance.repair import apply_fix
    with session_scope() as db:
        apply_fix(db, campaign_id=gc["campaign_id"], content_id=gc["content_id"],
                  reason_code="DISCLOSURE.PLATFORM_FIELD_MISSING")
    res2 = _decision(gc, run_mode="FULL_AUTO")
    assert res2["decision"] in ("ALLOW", "ALLOW_WITH_DISCLOSURE")


# ---- §128 voice clone w/o consent -> BLOCK -------------------- #

def test_voice_clone_without_consent_blocks(governed_campaign):
    gc = governed_campaign
    gc["add_asset"](asset_type="audio", source_type="GENERATED_AUDIO", voice_kind="CLONED_VOICE",
                    consent_status="UNKNOWN", ai_generated=True)
    res = _decision(gc, run_mode="FULL_AUTO")
    assert res["decision"] == "BLOCK" and res["hard_block"]
    assert "VOICE.CLONE_NO_CONSENT" in res["reason_codes"]


# ---- §129 fake endorsement -> BLOCK ------------------------- #

def test_fake_endorsement_blocks(governed_campaign):
    gc = governed_campaign
    gc["add_asset"](asset_type="image", source_type="GENERATED_IMAGE", person_status="SYNTHETIC_PERSON",
                    ai_generated=True, model_provider="x", model_terms_reference="t")
    with session_scope() as db:
        from app.db.models import Script
        db.query(Script).filter_by(campaign_id=gc["campaign_id"]).first().body += \
            " 유명 배우가 이 제품을 추천합니다. 지금 구매하세요."
    res = _decision(gc, run_mode="FULL_AUTO")
    assert res["decision"] == "BLOCK" and "ENDORSEMENT.PUBLIC_FIGURE" in res["reason_codes"]


# ---- §130 fact / chart mismatch -> BLOCK ------------------- #

def test_fact_visual_mismatch_blocks(governed_campaign):
    gc = governed_campaign
    with session_scope() as db:
        from app.db.models import Script, VerifiedFact
        db.query(Script).filter_by(campaign_id=gc["campaign_id"]).first().body = \
            "리서치에 따르면 번역 수요가 30% 줄었다."
        db.add(VerifiedFact(campaign_id=gc["campaign_id"], fact="번역 수요가 30% 줄었다",
                            status="VERIFIED", confidence=0.9, source_ids=["s9"], reason="출처"))
    # script says 30% but the chart backing that same claim shows 74
    res = _decision(gc, run_mode="FULL_AUTO", chart_values_by_claim={"0": [74]})
    assert res["decision"] == "BLOCK" and "CLAIM.CHART_MISMATCH" in res["reason_codes"]


# ---- §131 news media: fact ok, media rights unknown --------- #

def test_news_media_fact_vs_asset_rights_separated(governed_campaign):
    gc = governed_campaign
    # referencing a news article as a research SOURCE is fine (not modelled as an asset);
    # using the article's photo is a NEWS_MEDIA asset with unknown rights
    gc["add_asset"](asset_type="image", source_type="NEWS_MEDIA", source_url_or_id="https://news/x")
    res = _decision(gc, run_mode="FULL_AUTO")
    assert res["decision"] != "ALLOW"
    assert any("RIGHTS.UNKNOWN" in c for c in res["reason_codes"])


# ---- §132 music platform restriction -> TikTok BLOCK ------- #

def test_music_platform_restriction(governed_campaign):
    gc = governed_campaign
    gc["add_asset"](asset_type="music", source_type="MUSIC_LIBRARY", license_type="PROVIDER_MUSIC",
                    license_reference="m-1",
                    platform_restrictions={"youtube_shorts": True, "tiktok": False})
    with session_scope() as db:
        yt = govern_campaign(db, campaign_id=gc["campaign_id"], content_id=gc["content_id"],
                             platform="youtube_shorts", stage="pre_publish", run_mode="FULL_AUTO")
    with session_scope() as db:
        tt = govern_campaign(db, campaign_id=gc["campaign_id"], content_id=gc["content_id"],
                             platform="tiktok", stage="pre_publish", run_mode="FULL_AUTO")
    assert tt["decision"] == "BLOCK" and "RIGHTS.PLATFORM_RESTRICTED" in tt["reason_codes"]
    assert "RIGHTS.PLATFORM_RESTRICTED" not in yt["reason_codes"]


# ---- policy staleness -> FULL_AUTO review ------------------ #

def test_stale_policy_routes_disclosure_to_review(governed_campaign, _base_settings):
    gc = governed_campaign
    gc["add_asset"](asset_type="image", source_type="AI_GENERATED", ai_generated=True,
                    model_provider="x", model_terms_reference="t")
    with session_scope() as db:
        from app.db.models_gov import PolicyRegistry
        for r in db.query(PolicyRegistry).filter_by(platform="youtube_shorts"):
            r.last_verified_at = datetime.now(timezone.utc) - timedelta(days=999)
    res = _decision(gc, run_mode="FULL_AUTO")
    assert "POLICY.STALE" in res["reason_codes"]
    assert res["decision"] in ("HUMAN_REVIEW", "FIX_REQUIRED", "BLOCK")


# ---- clean AI-generated content passes ------------------- #

def test_clean_ai_content_passes_with_disclosure(governed_campaign):
    gc = governed_campaign
    gc["add_asset"](asset_type="image", source_type="AI_GENERATED", ai_generated=True,
                    model_provider="acme", model_name="img-v2", model_terms_reference="https://acme/terms")
    gc["add_asset"](asset_type="music", source_type="MUSIC_LIBRARY", license_type="PROVIDER_MUSIC",
                    license_reference="lic-ok")
    with session_scope() as db:
        from app.db.models import PlatformContent
        c = db.get(PlatformContent, gc["content_id"])
        c.payload = {**(c.payload or {}), "disclosure_meta": {"platform_ai_field": True}}
    res = _decision(gc, run_mode="FULL_AUTO")
    _bad = [s for s in res["sub_results"] if s["decision"] != "ALLOW"]
    assert res["publishable"] is True, _bad
    assert res["decision"] in ("ALLOW", "ALLOW_WITH_DISCLOSURE", "ALLOW_WITH_ATTRIBUTION"), _bad
