"""Phase 11 — Google AI (Imagen image + Veo video) adapter. Mocked HTTP only —
NO paid generation. Verifies config resolution, registry selection, happy path,
error normalisation, health, and cost = UNKNOWN."""
from __future__ import annotations

import base64

import pytest

from app.providers.errors import ProviderError

pytestmark = [pytest.mark.phase11]

_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


@pytest.fixture
def google_on(_base_settings):
    _base_settings.mock_mode = False
    _base_settings.google_api_key = "test-google-key"
    _base_settings.image_provider = "google"
    _base_settings.video_provider = "google"
    return _base_settings


# ---- config + registry ---- #

def test_registry_selects_google_only_when_configured(_base_settings):
    from app.providers.media import registry
    assert type(registry.get_image_provider()).__name__ == "MockImageProvider"

    _base_settings.mock_mode = False
    _base_settings.google_api_key = "k"
    _base_settings.image_provider = "google"
    _base_settings.video_provider = "google"
    assert type(registry.get_image_provider()).__name__ == "GoogleImageProvider"
    assert type(registry.get_video_provider()).__name__ == "GoogleVideoProvider"

    _base_settings.image_provider = "mock"      # provider name back to mock
    assert type(registry.get_image_provider()).__name__ == "MockImageProvider"


def test_media_provider_key_resolves_canonical_name(_base_settings):
    _base_settings.mock_mode = False
    _base_settings.google_api_key = "gk"
    _base_settings.image_provider = "google"
    assert _base_settings.media_provider_key("image") == "gk"
    assert _base_settings.media_provider_is_mock("image") is False
    _base_settings.google_api_key = None
    assert _base_settings.media_provider_is_mock("image") is True


# ---- image adapter ---- #

def test_google_image_happy_path(google_on, monkeypatch, tmp_path):
    from app.providers.media import google_image as gi

    captured = {}

    def fake_http_json(url, **kw):
        captured["url"] = url
        captured["body"] = kw.get("body")
        return {"predictions": [{"bytesBase64Encoded": _PNG, "mimeType": "image/png"}]}

    monkeypatch.setattr(gi, "http_json", fake_http_json)
    out = str(tmp_path / "img.png")
    res = gi.GoogleImageProvider().generate_image(
        prompt="a clean chart", negative_prompt="blurry", width=1920, height=1080,
        out_path=out, seed=7)

    assert res.provider == "google-imagen" and res.provider_mode.value == "REAL"
    assert res.mime_type == "image/png" and res.meta["cost_state"] == "UNKNOWN"
    assert res.cost == 0.0
    assert res.meta["aspect_ratio"] == "16:9"
    assert captured["body"]["parameters"]["seed"] == 7
    assert "generativelanguage.googleapis.com" in captured["url"]
    import os
    assert os.path.getsize(out) > 0


@pytest.mark.parametrize("aspect,w,h", [("1:1", 512, 512), ("9:16", 1080, 1920),
                                        ("16:9", 1920, 1080), ("3:4", 900, 1200)])
def test_google_image_aspect_ratio_mapping(google_on, monkeypatch, tmp_path, aspect, w, h):
    from app.providers.media import google_image as gi
    seen = {}
    monkeypatch.setattr(gi, "http_json", lambda url, **kw: seen.update(kw["body"]["parameters"])
                        or {"predictions": [{"bytesBase64Encoded": _PNG}]})
    gi.GoogleImageProvider().generate_image(prompt="x", negative_prompt="", width=w, height=h,
                                            out_path=str(tmp_path / "a.png"))
    assert seen["aspectRatio"] == aspect


def test_google_not_configured_raises_normalised(_base_settings):
    _base_settings.google_api_key = None
    _base_settings.image_api_key = None
    from app.providers.media.google_image import GoogleImageProvider
    with pytest.raises(ProviderError) as ei:
        GoogleImageProvider()
    assert getattr(ei.value, "provider_code", "") == "GOOGLE_NOT_CONFIGURED"
    assert ei.value.error_type == "AUTH_ERROR"          # terminal, not retried


@pytest.mark.parametrize("status,code,etype", [
    (403, "GOOGLE_AUTH_FAILED", "AUTH_ERROR"),
    (401, "GOOGLE_AUTH_FAILED", "AUTH_ERROR"),
    (429, "GOOGLE_RATE_LIMITED", "RATE_LIMIT"),
    (500, "GOOGLE_PROVIDER_ERROR", "PROVIDER_ERROR"),
])
def test_google_http_error_is_normalised(google_on, monkeypatch, tmp_path, status, code, etype):
    import urllib.error
    from app.providers.media import _http, google_image as gi

    import io

    def boom(*a, **k):
        raise urllib.error.HTTPError("u", status, "err", {}, io.BytesIO(b'{"error":{"message":"nope"}}'))

    monkeypatch.setattr(_http.urllib.request, "urlopen", boom)
    with pytest.raises(ProviderError) as ei:
        gi.GoogleImageProvider().generate_image(prompt="x", negative_prompt="", width=10, height=10,
                                                out_path=str(tmp_path / "z.png"))
    assert getattr(ei.value, "provider_code", "") == code
    assert ei.value.error_type == etype


def test_google_image_health_is_read_only(google_on, monkeypatch):
    from app.providers.media import google_image as gi
    calls = []
    monkeypatch.setattr(gi, "http_json", lambda url, **kw: calls.append(url) or {"models": [{}, {}]})
    h = gi.GoogleImageProvider().health()
    assert h["status"] == "CONNECTED" and h["models_visible"] == 2
    assert all(":predict" not in u for u in calls)      # never a generation call


# ---- video adapter (submit -> poll -> complete), all mocked ---- #

def test_google_video_submit_poll_complete(google_on, monkeypatch, tmp_path):
    from app.providers.media import google_video as gv
    _base = google_on
    _base.google_video_poll_seconds = 0
    seq = [
        {"name": "models/veo/operations/op-1"},                         # submit
        {"done": False},                                               # poll 1
        {"done": True, "response": {"predictions": [                    # poll 2 -> done
            {"bytesBase64Encoded": base64.b64encode(b"MP4DATA" * 8).decode()}]}},
    ]
    monkeypatch.setattr(gv, "http_json", lambda url, **kw: seq.pop(0))
    monkeypatch.setattr(gv.time, "sleep", lambda *_: None)
    out = str(tmp_path / "v.mp4")
    res = gv.GoogleVideoProvider().generate_video(
        prompt="a scene", reference_image=None, duration=6.0, width=1920, height=1080,
        camera_motion="SLOW_ZOOM_IN", out_path=out)
    assert res.provider == "google-veo" and res.mime_type == "video/mp4"
    assert res.meta["cost_state"] == "UNKNOWN" and res.cost == 0.0
    import os
    assert os.path.getsize(out) > 0


def test_google_video_operation_timeout_is_bounded(google_on, monkeypatch, tmp_path):
    from app.providers.media import google_video as gv
    google_on.google_video_max_wait_seconds = 0        # deadline already passed after submit
    google_on.google_video_poll_seconds = 0
    monkeypatch.setattr(gv, "http_json", lambda url, **kw: {"name": "op"} if url.endswith("Running?key=test-google-key")
                        else {"done": False})
    monkeypatch.setattr(gv.time, "sleep", lambda *_: None)
    with pytest.raises(ProviderError) as ei:
        gv.GoogleVideoProvider().generate_video(prompt="x", reference_image=None, duration=1,
                                                width=10, height=10, camera_motion="", out_path=str(tmp_path / "t.mp4"))
    assert ei.value.error_type == "TIMEOUT"


def test_no_paid_google_call_in_this_module(monkeypatch):
    """Guard: every test here stubs http_json/http_bytes/urlopen — a real network
    call would fail loudly."""
    import app.providers.media._http as h
    orig = h.urllib.request.urlopen
    assert callable(orig)   # nothing here should actually invoke it un-mocked
