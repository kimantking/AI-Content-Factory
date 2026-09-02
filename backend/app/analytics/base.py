from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"        # platform API does not expose it at all
    NOT_AUTHORIZED = "NOT_AUTHORIZED"  # needs a scope / tier / review the account lacks
    NOT_APPLICABLE = "NOT_APPLICABLE"  # metric is meaningless for this content type
    NOT_READY = "NOT_READY"            # too soon after publish


class AnalyticsErrorType(str, Enum):
    RATE_LIMIT = "RATE_LIMIT"
    AUTH_ERROR = "AUTH_ERROR"
    PERMISSION_MISSING = "PERMISSION_MISSING"
    METRIC_UNAVAILABLE = "METRIC_UNAVAILABLE"
    NOT_READY = "NOT_READY"
    TEMPORARY_ERROR = "TEMPORARY_ERROR"
    PLATFORM_ERROR = "PLATFORM_ERROR"


class AnalyticsError(Exception):
    def __init__(self, error_type: AnalyticsErrorType, message: str,
                 metric: str | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.error_type = error_type
        self.metric = metric
        self.retry_after = retry_after


class MetricValue(BaseModel):
    normalized_name: str
    value: float | int | None = None
    availability: Availability = Availability.AVAILABLE
    unit: str = "count"
    raw_name: str | None = None
    note: str = ""

    @property
    def usable(self) -> bool:
        return self.availability == Availability.AVAILABLE and self.value is not None


class PostMetrics(BaseModel):
    platform: str
    remote_post_id: str
    collected_at: str
    content_age_minutes: int = 0
    window_label: str = ""
    data_source: str = "PLATFORM_API"     # PLATFORM_API | MANUAL_IMPORT | CSV_IMPORT | ESTIMATE
    provider: str = "mock"
    provider_mode: str = "MOCK"
    collection_status: str = "SUCCESS"    # SUCCESS | PARTIAL | FAILED | UNAVAILABLE
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    raw_payload: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

    def value(self, name: str):
        mv = self.metrics.get(name)
        return mv.value if (mv and mv.usable) else None

    def availability_map(self) -> dict[str, str]:
        return {k: v.availability.value for k, v in self.metrics.items()}


@runtime_checkable
class AnalyticsProvider(Protocol):
    platform: str
    provider_mode: str

    def get_capabilities(self) -> dict: ...
    def validate_permissions(self, account: dict) -> tuple[bool, list[str]]: ...
    def get_post_metrics(self, remote_post_id: str, *, content_type: str,
                         content_age_minutes: int, window_label: str) -> PostMetrics: ...
    def get_account_metrics(self, account_id: str) -> dict: ...
    def get_audience_metrics(self, account_id: str) -> dict: ...
    def get_revenue_metrics(self, remote_post_id: str, *, content_age_minutes: int) -> MetricValue: ...
    def normalize_metrics(self, raw: dict) -> dict[str, MetricValue]: ...
