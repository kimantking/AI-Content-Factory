from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.analytics.base import Availability
from app.publishing.capabilities import resolve_publishing_platform

_PATH = Path(__file__).with_name("capabilities.json")


@dataclass(frozen=True)
class AnalyticsCapability:
    platform: str
    official_api: str
    required_scope: list[str]
    account_requirement: str
    historical_support: bool
    revenue_support: bool
    analytics_delay: str
    known_limitations: str
    metrics: dict            # api_metric_name -> Availability value string
    last_verified_at: str = ""

    def availability(self, api_metric: str) -> Availability:
        v = self.metrics.get(api_metric)
        return Availability(v) if v else Availability.UNAVAILABLE

    def available_metrics(self) -> list[str]:
        return [k for k, v in self.metrics.items() if v == Availability.AVAILABLE.value]


@lru_cache
def load_analytics_capabilities() -> dict[str, AnalyticsCapability]:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    verified = raw.get("last_verified_at", "")
    out: dict[str, AnalyticsCapability] = {}
    for row in raw.get("platforms", []):
        out[row["platform"]] = AnalyticsCapability(
            platform=row["platform"], official_api=row["official_api"],
            required_scope=row.get("required_scope", []),
            account_requirement=row.get("account_requirement", ""),
            historical_support=row.get("historical_support", False),
            revenue_support=row.get("revenue_support", False),
            analytics_delay=row.get("analytics_delay", ""),
            known_limitations=row.get("known_limitations", ""),
            metrics=row.get("metrics", {}),
            last_verified_at=verified,
        )
    return out


def get_analytics_capability(platform: str) -> AnalyticsCapability:
    caps = load_analytics_capabilities()
    key = platform.strip().lower()
    if key not in caps:
        key = resolve_publishing_platform(key)
    if key.startswith("naver"):
        key = "naver_blog" if key not in caps else key
    if key not in caps:
        raise KeyError(f"no analytics capability for platform {platform!r}")
    return caps[key]
