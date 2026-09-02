from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name("capabilities.json")


@dataclass(frozen=True)
class TrendCapability:
    source_id: str
    name: str
    source_type: str
    provider: str
    auth_status: str
    freshness: str
    reliability: float
    cost: str
    known_limitations: str
    last_verified_at: str = ""

    @property
    def usable(self) -> bool:
        return self.auth_status in ("AVAILABLE",)  # only OWN_ANALYTICS by default


@lru_cache
def load_trend_capabilities() -> dict[str, TrendCapability]:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    verified = raw.get("last_verified_at", "")
    out: dict[str, TrendCapability] = {}
    for row in raw.get("sources", []):
        out[row["source_id"]] = TrendCapability(
            source_id=row["source_id"], name=row["name"], source_type=row["source_type"],
            provider=row["provider"], auth_status=row["auth_status"],
            freshness=row.get("freshness", ""), reliability=row.get("reliability", 0.5),
            cost=row.get("cost", ""), known_limitations=row.get("known_limitations", ""),
            last_verified_at=verified,
        )
    return out


def get_trend_capability(source_id: str) -> TrendCapability:
    caps = load_trend_capabilities()
    if source_id not in caps:
        raise KeyError(f"no trend capability for {source_id!r}")
    return caps[source_id]
