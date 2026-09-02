from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class TrendProviderStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    LIMITED = "LIMITED"
    DISABLED = "DISABLED"
    UNAVAILABLE = "UNAVAILABLE"


class TrendSourceType(str, Enum):
    OFFICIAL_API = "OFFICIAL_API"
    APPROVED_API = "APPROVED_API"
    PUBLIC_SEARCH = "PUBLIC_SEARCH"
    OWN_ANALYTICS = "OWN_ANALYTICS"
    MANUAL = "MANUAL"
    OPTIONAL = "OPTIONAL"


class TrendError(Exception):
    def __init__(self, message: str, error_type: str = "PROVIDER_ERROR", retry_after: float | None = None):
        super().__init__(message)
        self.error_type = error_type
        self.retry_after = retry_after


class RawTrend(BaseModel):
    source_id: str
    raw_topic: str
    title: str = ""
    description: str = ""
    published_at: str | None = None
    country: str = "KR"
    language: str = "ko"
    # time-bucketed interest, used for velocity/acceleration
    interest_series: dict[str, float] = Field(default_factory=dict)   # {"1h":..,"6h":..,"24h":..,"3d":..,"7d":..,"30d":..}
    engagement_signals: dict = Field(default_factory=dict)
    source_metrics: dict = Field(default_factory=dict)
    url: str | None = None
    reliability: str = "unknown"
    raw_payload: dict = Field(default_factory=dict)


@runtime_checkable
class TrendProvider(Protocol):
    source_id: str
    provider_mode: str

    def get_capabilities(self) -> dict: ...
    def fetch_trending(self, *, country: str, language: str, limit: int) -> list[RawTrend]: ...
    def search_topic(self, query: str, *, country: str, language: str) -> list[RawTrend]: ...
    def get_topic_history(self, topic: str) -> dict: ...
    def get_velocity_data(self, topic: str) -> dict: ...
    def get_source_metadata(self) -> dict: ...
