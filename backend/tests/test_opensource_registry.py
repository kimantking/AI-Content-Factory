from __future__ import annotations

from app.opensource import load_registry
from app.opensource.registry import USAGE_TYPES


def test_registry_loads_and_is_well_formed():
    comps = load_registry()
    assert len(comps) >= 8
    names = {c.name for c in comps}
    assert {"MoneyPrinterTurbo", "whisperX", "PySceneDetect", "Remotion",
            "blader/humanizer", "edge-tts"} <= names
    for c in comps:
        assert c.usage_type in USAGE_TYPES
        assert c.repository.startswith("https://github.com/")
        assert c.license


def test_commercially_sensitive_components_flagged():
    by_name = {c.name: c for c in load_registry()}
    assert by_name["Remotion"].commercial_review_status == "REVIEW_REQUIRED"
    assert by_name["edge-tts"].can_use_directly is False
    assert by_name["blader/humanizer"].usage_type == "REFERENCE_IMPLEMENTATION"
