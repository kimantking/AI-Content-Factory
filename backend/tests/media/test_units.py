from __future__ import annotations

import wave

import pytest

from app.media.chart import ChartDataError, render_chart
from app.media.subtitles import build_blocks, phrase_units, write_srt
from app.media.thumbnail import propose_concepts, render_concept
from app.media.visual_director import plan_visuals
from app.media.word_timing import EstimatorAlignmentProvider, get_alignment_provider
from app.platforms import ALL_PLATFORMS, get_platform
from app.providers.media import media_provider_status
from app.providers.media.cache import AssetCache, asset_hash
from app.providers.media.mock_image import MockImageProvider
from app.providers.media.mock_music import MockMusicProvider
from app.providers.media.mock_tts import MockTTSProvider, estimate_seconds
from app.providers.media.manager import ProviderManager, ProviderRecord
from app.providers.errors import AuthError, ProviderError
from app.schemas.media import ChartSpec, WordTiming


# ---- platform registry --------------------------------------------------- #

def test_platform_registry_and_aliases():
    assert len(ALL_PLATFORMS) >= 13
    assert get_platform("YouTube Shorts").key == "youtube_shorts"
    assert get_platform("instagram").key == "instagram_reel"
    assert get_platform("naver_clip").resolution() == (1080, 1920)
    assert get_platform("instagram_feed").resolution() == (1080, 1350)


# ---- visual director (cost-aware) -------------------------------------- #

def test_visual_director_downgrades_ai_video_without_provider():
    scenes = [{"narration": "변화가 빠르게 밀려온다", "source_ids": []}]
    ch = plan_visuals(scenes, max_ai_video_ratio=0.5, video_provider_available=False,
                      stock_provider_available=True, remaining_budget_usd=100)[0]
    assert ch.visual_type == "AI_IMAGE"
    assert ch.downgraded_from == "AI_VIDEO"


def test_visual_director_chart_requires_sources_and_varies_motion():
    scenes = [
        {"narration": "번역 수요가 20% 감소했다 비교하면", "source_ids": ["s1"]},
        {"narration": "숫자 30% 대비 증가", "source_ids": []},
        {"narration": "일반적인 설명 문장", "source_ids": []},
        {"narration": "또 다른 설명", "source_ids": []},
    ]
    out = plan_visuals(scenes, max_ai_video_ratio=0.0, video_provider_available=False,
                       stock_provider_available=False, remaining_budget_usd=0)
    assert out[0].visual_type == "CHART"
    assert out[1].visual_type == "TEXT_CARD"          # numbers but no source -> text card
    assert len({c.camera_motion for c in out}) >= 3    # motion variety


# ---- word timing ------------------------------------------------------- #

def test_estimator_alignment_covers_full_duration_and_is_monotonic():
    wt = EstimatorAlignmentProvider().align(
        text="첫 문장 입니다. 두 번째 조금 더 길게 이어집니다.", audio_path="", total_duration=6.0)
    assert wt[0].start == 0.0
    assert abs(wt[-1].end - 6.0) < 0.01
    assert all(a.end <= b.start + 1e-6 for a, b in zip(wt, wt[1:]))


def test_alignment_provider_falls_back_when_whisperx_absent(_base_settings):
    _base_settings.alignment_provider = "whisperx"
    assert get_alignment_provider().name == "estimator"


# ---- subtitles ------------------------------------------------------- #

def test_phrase_units_break_after_particles():
    units = phrase_units("인공지능이 앞으로 직업을 어떻게 바꿀까요 그리고 우리는 무엇을 준비해야 할까요")
    assert len(units) >= 2
    assert all(u.strip() for u in units)


def test_build_blocks_and_srt(tmp_path):
    words = [WordTiming(word=w, start=i * 0.5, end=i * 0.5 + 0.5)
             for i, w in enumerate("번역 수요가 3년간 20% 줄었고 대응 시간은 있다".split())]
    blocks = build_blocks(words, max_chars=12, highlight_terms=[])
    assert blocks
    assert any("20%" in b.highlight_words or "3년간" in " ".join(b.highlight_words) for b in blocks) or \
           any("%" in b.text for b in blocks)
    srt = write_srt(blocks, str(tmp_path / "c.srt"))
    body = open(srt, encoding="utf-8").read()
    assert "-->" in body and body.strip().startswith("1")


# ---- asset cache ----------------------------------------------------- #

def test_asset_hash_stable_and_cache_roundtrip(tmp_path, _base_settings):
    _base_settings.asset_cache_enabled = True
    _base_settings.storage_root = str(tmp_path)
    k1 = asset_hash(provider="p", model="m", prompt="a cat", settings={"w": 10}, aspect_ratio="1:1")
    k2 = asset_hash(provider="p", model="m", prompt="a cat", settings={"w": 10}, aspect_ratio="1:1")
    assert k1 == k2
    src = tmp_path / "src.png"
    src.write_bytes(b"x" * 32)
    c = AssetCache()
    c.put(k1, str(src))
    dst = tmp_path / "dst.png"
    assert c.get(k1, str(dst)) is True
    assert dst.read_bytes() == b"x" * 32


# ---- mock media providers ----------------------------------------- #

def test_mock_image_writes_real_png(tmp_path):
    out = tmp_path / "x.png"
    r = MockImageProvider().generate_image(prompt="도시 거리", negative_prompt="", width=640,
                                           height=1136, out_path=str(out), seed=1)
    assert out.stat().st_size > 1000
    assert r.provider_mode.value == "MOCK" and r.width == 640
    from PIL import Image

    assert Image.open(out).size == (640, 1136)


def test_mock_tts_duration_matches_estimate(tmp_path):
    text = "이것은 타이밍을 확인하기 위한 문장입니다 조금 더 길게 이어서 말합니다"
    out = tmp_path / "v.wav"
    r = MockTTSProvider().synthesize(text=text, voice_id="k", language="ko", speed=1.0,
                                     emotion="", style="", out_path=str(out))
    with wave.open(str(out)) as w:
        actual = w.getnframes() / w.getframerate()
    assert abs(actual - estimate_seconds(text)) < 0.05
    assert abs(r.duration - actual) < 0.05


def test_mock_music_has_license_metadata(tmp_path):
    r = MockMusicProvider().get_track(mood="AMBIENT", duration=3.0, out_path=str(tmp_path / "m.wav"))
    assert r.meta["commercial_use_allowed"] is True
    assert r.meta["license_type"] and r.meta["source"] == "generated"


def test_provider_status_marks_video_disabled():
    st = {row["kind"]: row for row in media_provider_status()}
    assert st["image"]["mode"] == "MOCK"
    assert st["video"]["mode"] == "DISABLED"       # no real video provider in Phase 1-B


# ---- provider manager --------------------------------------------- #

def test_provider_manager_falls_back_then_raises():
    class Bad:
        def go(self):
            raise ProviderError("boom", error_type="TIMEOUT")

    class Good:
        def go(self):
            return "ok"

    mgr = ProviderManager(kind="image")
    mgr.add(ProviderRecord(name="bad", provider=Bad(), priority=1, max_retry=2))
    mgr.add(ProviderRecord(name="good", provider=Good(), priority=2, max_retry=1))
    result, rec = mgr.call(lambda p: p.go())
    assert result == "ok" and rec.name == "good"


def test_provider_manager_does_not_retry_auth():
    class Auth:
        def go(self):
            raise AuthError("nope")

    mgr = ProviderManager(kind="tts")
    mgr.add(ProviderRecord(name="a", provider=Auth(), priority=1, max_retry=3))
    with pytest.raises(ProviderError):
        mgr.call(lambda p: p.go())


# ---- chart ------------------------------------------------------ #

def test_chart_renders_and_requires_sources(tmp_path):
    ok = ChartSpec(chart_type="bar", title="t", labels=["A", "B"], values=[1, 2], source_ids=["s1"])
    p = render_chart(ok, str(tmp_path / "c.png"), width=600, height=600)
    assert open(p, "rb").read(8).startswith(b"\x89PNG")
    with pytest.raises(ChartDataError):
        render_chart(ChartSpec(labels=["A"], values=[1], source_ids=[]), str(tmp_path / "b.png"))


# ---- thumbnail ------------------------------------------------ #

def test_thumbnail_concepts_and_render(tmp_path):
    concepts = propose_concepts("AI 직업", "대응 시간은 있다", "지금 바뀌고 있다")
    assert len(concepts) == 3
    c = render_concept(concepts[0], str(tmp_path / "t.png"))
    assert set(c.scores) >= {"clarity", "curiosity", "readability"}
    assert (tmp_path / "t.png").stat().st_size > 1000
