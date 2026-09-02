from __future__ import annotations

from app.analytics.base import AnalyticsError, AnalyticsErrorType, MetricValue, PostMetrics
from app.analytics.capabilities import get_analytics_capability
from app.analytics.mock_analytics import MockAnalyticsClient, build_post_metrics
from app.analytics.metric_catalog import normalize
from app.config import get_settings


class MockAnalyticsFetchClient(MockAnalyticsClient):
    pass


class HttpAnalyticsClient:
    """Real client placeholder — raises until per-platform credentials + adapters
    are wired. Never fabricates metrics."""

    mode = "REAL"

    def fetch(self, *_a, **_k):
        raise AnalyticsError(AnalyticsErrorType.PERMISSION_MISSING,
                             "real analytics client not configured — credentials + adapter required")

    account = audience = fetch


def _client():
    if get_settings().analytics_client == "http":
        return HttpAnalyticsClient()
    return MockAnalyticsFetchClient()


class PlatformAnalyticsProvider:
    platform = "generic"

    def __init__(self, client=None):
        self.client = client or _client()
        self.provider_mode = self.client.mode
        self.cap = get_analytics_capability(self.platform)

    # -- interface -------------------------------------------------------
    def get_capabilities(self) -> dict:
        return {
            "platform": self.platform, "official_api": self.cap.official_api,
            "available_metrics": self.cap.available_metrics(),
            "revenue_support": self.cap.revenue_support,
            "historical_support": self.cap.historical_support,
            "analytics_delay": self.cap.analytics_delay,
            "known_limitations": self.cap.known_limitations,
            "provider_mode": self.provider_mode,
        }

    def validate_permissions(self, account: dict) -> tuple[bool, list[str]]:
        errs: list[str] = []
        if account.get("connection_status") != "CONNECTED":
            errs.append("account not CONNECTED")
        have = set(account.get("scopes") or [])
        need = {s.split(" ")[0] for s in self.cap.required_scope}
        missing = need - have
        if missing:
            errs.append(f"missing analytics scopes: {sorted(missing)}")
        return (not errs, errs)

    def get_post_metrics(self, remote_post_id: str, *, content_type: str,
                         content_age_minutes: int, window_label: str,
                         feature_hint: dict | None = None) -> PostMetrics:
        raw = self.client.fetch(self.platform, remote_post_id,
                                content_age_minutes=content_age_minutes,
                                feature_hint=feature_hint)
        return build_post_metrics(
            self.platform, remote_post_id, content_type=content_type,
            content_age_minutes=content_age_minutes, window_label=window_label,
            raw=raw, provider=f"{self.platform}-analytics", provider_mode=self.provider_mode,
        )

    def get_account_metrics(self, account_id: str) -> dict:
        return self.client.account(self.platform, account_id)

    def get_audience_metrics(self, account_id: str) -> dict:
        return self.client.audience(self.platform, account_id)

    def get_revenue_metrics(self, remote_post_id: str, *, content_age_minutes: int) -> MetricValue:
        if not self.cap.revenue_support:
            return MetricValue(normalized_name="estimated_revenue", value=None,
                               availability=self.cap.availability("estimatedRevenue")
                               if "estimatedRevenue" in self.cap.metrics else
                               __import__("app.analytics.base", fromlist=["Availability"]).Availability.UNAVAILABLE)
        raw = self.client.fetch(self.platform, remote_post_id,
                                content_age_minutes=content_age_minutes)
        return normalize(self.platform, raw).get(
            "estimated_revenue",
            MetricValue(normalized_name="estimated_revenue", value=None),
        )

    def normalize_metrics(self, raw: dict) -> dict[str, MetricValue]:
        return normalize(self.platform, raw)


class YouTubeAnalyticsProvider(PlatformAnalyticsProvider):
    platform = "youtube"


class TikTokAnalyticsProvider(PlatformAnalyticsProvider):
    platform = "tiktok"


class InstagramAnalyticsProvider(PlatformAnalyticsProvider):
    platform = "instagram"


class FacebookAnalyticsProvider(PlatformAnalyticsProvider):
    platform = "facebook"


class ThreadsAnalyticsProvider(PlatformAnalyticsProvider):
    platform = "threads"


class XAnalyticsProvider(PlatformAnalyticsProvider):
    platform = "x"


class PinterestAnalyticsProvider(PlatformAnalyticsProvider):
    platform = "pinterest"


class LinkedInAnalyticsProvider(PlatformAnalyticsProvider):
    platform = "linkedin"


class NaverAnalyticsProvider(PlatformAnalyticsProvider):
    platform = "naver_blog"

    def get_post_metrics(self, remote_post_id: str, **kw) -> PostMetrics:
        # No official analytics API -> everything UNAVAILABLE; manual/CSV import only.
        from app.analytics.base import Availability

        pm = super().get_post_metrics(remote_post_id, **kw)
        pm.collection_status = "UNAVAILABLE"
        pm.data_source = "CSV_IMPORT"
        for mv in pm.metrics.values():
            mv.value = None
            if mv.availability == Availability.AVAILABLE:
                mv.availability = Availability.UNAVAILABLE
        return pm
