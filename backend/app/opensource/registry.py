from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_REGISTRY_PATH = Path(__file__).with_name("registry.json")

USAGE_TYPES = {
    "DIRECT_DEPENDENCY",
    "REFERENCE_IMPLEMENTATION",
    "ALGORITHM_REFERENCE",
    "OPTIONAL_TOOL",
}


@dataclass(frozen=True)
class OpenSourceComponent:
    name: str
    repository: str
    version: str
    license: str
    usage_type: str
    feature: str = ""
    can_use_directly: bool = False
    reference_only: bool = True
    attribution_required: bool = False
    commercial_review_status: str = "REVIEW_REQUIRED"
    notes: str = ""


@lru_cache
def load_registry() -> list[OpenSourceComponent]:
    data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    out: list[OpenSourceComponent] = []
    for c in data.get("components", []):
        fields = {k: c.get(k) for k in OpenSourceComponent.__dataclass_fields__ if k in c}
        comp = OpenSourceComponent(**fields)
        assert comp.usage_type in USAGE_TYPES, f"bad usage_type: {comp.usage_type}"
        out.append(comp)
    return out
