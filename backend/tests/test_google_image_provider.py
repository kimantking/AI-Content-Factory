import base64

from app.providers.media.google_image import _effective_model, _image_part


def test_retired_imagen_setting_migrates_to_current_model():
    assert _effective_model("imagen-3.0-generate-002") == "gemini-3.1-flash-image"
    assert _effective_model("imagen-4.0-generate-001") == "gemini-3.1-flash-image"
    assert _effective_model("gemini-3-pro-image") == "gemini-3-pro-image"


def test_native_image_response_is_decoded():
    raw = b"png-data"
    data = {
        "candidates": [{
            "content": {
                "parts": [{
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": base64.b64encode(raw).decode(),
                    }
                }]
            }
        }]
    }

    image, mime = _image_part(data)
    assert image == raw
    assert mime == "image/png"
