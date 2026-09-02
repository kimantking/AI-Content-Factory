from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import session_scope
from app.governance import claims as _cl
from app.governance import disclosure as _disc
from app.governance import identity as _id
from app.governance import originality as _orig
from app.governance import phash as _ph
from app.governance.decision import GovernanceDecision, decide, valid_transition
from app.governance.licenses import commercial_ok, interpret
from app.governance.rights import record_asset_rights, resolve_status


# ---- license registry (§8, §9) --------------------------------------- #

def test_license_interpretation_and_code_vs_content(_seed_registries):
    with session_scope() as db:
        assert interpret(db, "CC0")["commercial_allowed"] == "YES"
        assert interpret(db, "CC-BY")["attribution_required"] is True
        assert interpret(db, "CC-BY-NC")["commercial_allowed"] == "NO"
        # a SOFTWARE license used for an ASSET is UNKNOWN for that asset (§9)
        assert commercial_ok(db, "MIT") == "UNKNOWN"
        assert interpret(db, "SOMETHING_WE_NEVER_SAW")["commercial_allowed"] == "UNKNOWN"


# ---- rights status resolution (§3, §120, §121, §123) --------------- #

@pytest.mark.parametrize("source_type,kw,expect", [
    ("USER_UPLOAD", {"user_supplied": True}, "UNKNOWN_RIGHTS"),
    ("USER_UPLOAD", {"user_supplied": True, "notes": ""}, "UNKNOWN_RIGHTS"),
    ("STOCK_LICENSED", {"license_type": "COMMERCIAL_STOCK", "license_reference": "receipt-1"}, "LICENSED"),
    ("STOCK_LICENSED", {"license_type": "EDITORIAL_STOCK", "license_reference": "e-1"}, "RESTRICTED"),
    ("PUBLIC_DOMAIN", {"license_type": "PUBLIC_DOMAIN"}, "PUBLIC_DOMAIN_VERIFIED"),
    ("AI_GENERATED", {"model_provider": "acme", "model_terms_reference": "terms-url"}, "AI_GENERATED_VERIFIED"),
    ("AI_GENERATED", {}, "UNKNOWN_RIGHTS"),
    ("SCREENSHOT", {"source_url_or_id": "https://x/y"}, "UNKNOWN_RIGHTS"),
    ("NEWS_MEDIA", {}, "UNKNOWN_RIGHTS"),
])
def test_rights_status_matrix(_seed_registries, source_type, kw, expect):
    with session_scope() as db:
        led = record_asset_rights(db, asset_id=f"a-{source_type}-{hash(str(kw))%9999}",
                                  source_type=source_type, **kw)
        assert led.rights_status == expect


def test_expired_license_is_expired(_seed_registries):
    with session_scope() as db:
        led = record_asset_rights(db, asset_id="a-exp", source_type="STOCK_LICENSED",
                                  license_type="COMMERCIAL_STOCK", license_reference="r",
                                  expiration_at=datetime.now(timezone.utc) - timedelta(days=1))
        assert led.rights_status == "EXPIRED"


def test_watermarked_asset_is_blocked(_seed_registries):
    with session_scope() as db:
        led = record_asset_rights(db, asset_id="a-wm", source_type="STOCK_LICENSED",
                                  license_type="COMMERCIAL_STOCK", license_reference="r",
                                  watermark_detected=True)
        assert led.rights_status == "BLOCKED"


def test_cloned_voice_without_consent_is_blocked(_seed_registries):
    with session_scope() as db:
        led = record_asset_rights(db, asset_id="a-vc", source_type="GENERATED_AUDIO",
                                  voice_kind="CLONED_VOICE", consent_status="UNKNOWN")
        assert led.rights_status == "BLOCKED"
        assert _id.voice_clone_guard(led)["verdict"] == "BLOCK"
    with session_scope() as db:
        led2 = record_asset_rights(db, asset_id="a-vc2", source_type="GENERATED_AUDIO",
                                   voice_kind="CLONED_VOICE", consent_status="DOCUMENTED",
                                   model_terms_reference="provider-terms")
        assert _id.voice_clone_guard(led2)["verdict"] == "OK"


# ---- attribution does not fix rights (§66) ----------------------- #

def test_attribution_does_not_create_rights(_seed_registries):
    from app.governance.attribution import build_attribution_package
    with session_scope() as db:
        led = record_asset_rights(db, asset_id="a-noright", source_type="USER_UPLOAD",
                                  user_supplied=True, attribution_required=True,
                                  attribution_text="Photo by X")
        assert led.rights_status == "UNKNOWN_RIGHTS"
        pkg = build_attribution_package(db, campaign_id=led.campaign_id or "x")
        # the item is present but flagged unusable
        assert not any(i["usable"] for i in pkg["items"] if i["asset_id"] == "a-noright") or pkg["unusable_assets"]


# ---- decision engine + state machine (§78, §79, §116) ----------- #

def test_decision_block_is_hard_and_not_agent_overridable():
    subs = [
        {"engine": "rights", "decision": "BLOCK", "reason_codes": ["RIGHTS.WATERMARK"], "hard_block": True},
        {"engine": "originality", "decision": "ALLOW", "reason_codes": []},
    ]
    d = decide(subs)
    assert d.decision == "BLOCK" and d.hard_block is True
    from app.governance.decision import apply_human_override
    new, err = apply_human_override(d, reviewer="alice", approve=True)
    assert err and new.decision == "BLOCK"          # hard block survives a UI approve


def test_soft_review_is_overridable():
    d = decide([{"engine": "policy", "decision": "HUMAN_REVIEW", "reason_codes": ["POLICY.STALE"]}])
    from app.governance.decision import apply_human_override
    new, err = apply_human_override(d, reviewer="bob", approve=True)
    assert err is None and new.publishable


def test_state_machine_rejects_invalid_transition():
    assert valid_transition("SCANNING", "BLOCKED")
    assert valid_transition("BLOCKED", "SCANNING")
    assert not valid_transition("RESOLVED", "PASS")
    assert not valid_transition("PENDING", "PASS")


# ---- disclosure engine (§31-§34, §127) ------------------------- #

def test_disclosure_decision_by_platform(_seed_registries):
    with session_scope() as db:
        prov = {"synthetic_video": True, "ai_generated": True, "materially_altered": False}
        yt = _disc.decide(db, platform="youtube_shorts", provenance=prov)
        assert yt["decision"] == "PLATFORM_FIELD_REQUIRED"
        li = _disc.decide(db, platform="linkedin", provenance={"ai_generated": True})
        assert li["decision"] in ("RECOMMENDED", "NOT_REQUIRED")
        rp = _disc.decide(db, platform="tiktok",
                          provenance={"real_person_synthetic": True, "ai_generated": True})
        assert rp["decision"] == "HUMAN_REVIEW"


def test_disclosure_not_stripped_guard():
    v = _disc.assert_not_stripped({"disclosure_required": True, "disclosure_text": "AI 생성 포함"},
                                  {"disclosure_required": False, "disclosure_text": ""})
    assert v
    assert _disc.strip_disclosure_from_text_guard("이 콘텐츠에는 AI가 생성한 요소가 있습니다.", "그냥 일반 문장")


# ---- claim governance (§52, §130) ----------------------------- #

def test_statistic_must_trace_and_chart_must_match():
    ok = _cl.validate_statistic("번역 수요가 20% 감소했다", usable_fact_texts=["수요가 20% 줄었다"],
                                chart_values=[20, 80])
    assert ok["status"] == "OK"
    mismatch = _cl.validate_statistic("번역 수요가 47% 감소했다",
                                     usable_fact_texts=["수요가 47% 줄었다"], chart_values=[74])
    assert mismatch["status"] == "MISMATCH"
    unbacked = _cl.validate_statistic("실업률은 99% 상승했다", usable_fact_texts=["수요가 20% 줄었다"])
    assert unbacked["status"] == "UNSUPPORTED"


def test_opinion_not_stated_as_fact():
    r = _cl.validate_opinion_as_fact("전문가들은 반드시 이렇게 될 거라고 본다")
    assert r["status"] == "OPINION_AS_FACT"
    assert _cl.classify_claim('"이것은 사실이다"라고 말했다') == "QUOTE"
    assert _cl.validate_quote('그는 "내일 발표한다"라고 말했다', source_ids=[])["status"] == "UNSUPPORTED"


def test_temporal_validity():
    old = _cl.temporal_validity("현재 시가총액 1위 기업", verified_at=datetime.now(timezone.utc) - timedelta(days=400))
    assert old["status"] == "STALE"
    dev = _cl.temporal_validity("가격이 방금 바뀌었다", verified_at=datetime.now(timezone.utc), event_status="DEVELOPING")
    assert dev["status"] == "STALE"


# ---- originality V2 (§17-§28, §124) -------------------------- #

def test_text_similarity_multi_metric_catches_paraphrase():
    a = "AI가 대체할 직업 5가지 정리"
    b = "인공지능으로 대체될 직업 5가지 총정리"       # heavier lexical overlap paraphrase
    sim = _orig.text_similarity(a, b)
    # exact/normalised hashing miss it; the multi-metric combined score does not
    assert sim["exact"] == 0.0 and sim["norm"] == 0.0
    assert sim["combined"] > sim["norm"] and sim["combined"] >= 0.3
    same = _orig.text_similarity(a, a)
    assert same["combined"] == 1.0 and same["exact"] == 1.0
    # NOTE: the cheap hashed embedding limits far-paraphrase recall — a real
    # EmbeddingProvider (DECISIONS D61) would raise this; documented, not hidden.


def test_video_fingerprint_survives_reencode_and_recolour():
    scenes = [{"estimated_duration": 4.0, "visual_type": "AI_IMAGE", "camera_motion": "SLOW_ZOOM_IN"},
              {"estimated_duration": 5.0, "visual_type": "CHART", "camera_motion": "KEN_BURNS"},
              {"estimated_duration": 4.0, "visual_type": "STOCK_VIDEO", "camera_motion": "PAN_LEFT"}]
    fp1 = _orig.build_video_fingerprint(scenes, duration=13.0)
    # "re-encode + crop + subtitle colour change" => same structure, tiny duration wobble
    fp2 = _orig.build_video_fingerprint(scenes, duration=12.7)
    assert _orig.video_fp_similarity(fp1, fp2) >= 0.9
    # a genuinely different edit
    other = [{"estimated_duration": 2.0, "visual_type": "AI_VIDEO", "camera_motion": "PAN_RIGHT"}] * 6
    fp3 = _orig.build_video_fingerprint(other, duration=12.0)
    assert _orig.video_fp_similarity(fp1, fp3) < 0.6


def test_transformation_and_reuse_risk():
    tr = _orig.transformation_score(
        script_body="직접 설명하자면, 데이터를 분석해보면 배경 맥락이 중요하다. 제 생각에는 이렇다.",
        scenes=[{}] * 5, visual_types=["CHART", "TEXT_CARD", "AI_IMAGE", "STOCK_VIDEO"])
    assert tr["score"] > 0.4
    reuse = _orig.reused_content_risk(visual_types=["STOCK_VIDEO"] * 8, external_footage_ratio=0.9,
                                     transformation=0.1)
    assert reuse["verdict"] == "BLOCK"


def test_phash_of_resized_image_is_similar(tmp_path):
    from PIL import Image
    import random as _r
    rnd = _r.Random(3)
    img = Image.new("RGB", (600, 600))
    img.putdata([(rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)) for _ in range(600 * 600)])
    p1 = str(tmp_path / "o.png"); img.save(p1)
    p2 = str(tmp_path / "r.jpg"); img.resize((240, 240)).save(p2, quality=70)
    p3 = str(tmp_path / "d.png")
    img2 = Image.new("RGB", (600, 600))
    img2.putdata([(rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)) for _ in range(600 * 600)])
    img2.save(p3)
    assert _ph.similarity(_ph.phash(p1), _ph.phash(p2)) >= 0.85
    assert _ph.similarity(_ph.phash(p1), _ph.phash(p3)) < 0.75


# ---- identity guards (§41, §45) ----------------------------- #

def test_fake_endorsement_guard(_seed_registries):
    with session_scope() as db:
        led = record_asset_rights(db, asset_id="a-fig", source_type="GENERATED_IMAGE",
                                  person_status="SYNTHETIC_PERSON", model_provider="x",
                                  model_terms_reference="t")
        r = _id.fake_endorsement_guard(
            script_text="유명 배우가 이 제품을 추천합니다. 지금 구매하세요.", asset_ledgers=[led])
        assert r["verdict"] == "BLOCK" and r["severity"] == "CRITICAL"


def test_pii_scan():
    assert _id.scan_pii("연락처 010-1234-5678")["verdict"] == "HUMAN_REVIEW"
    assert _id.scan_pii("카드번호 4111 1111 1111 1111")["verdict"] == "BLOCK"
    assert _id.scan_pii("일반 텍스트")["verdict"] == "OK"
