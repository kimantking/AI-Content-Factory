from __future__ import annotations

from app.config import get_settings
from app.trends.base import RawTrend, TrendError
from app.trends.capabilities import get_trend_capability
from app.trends.faults import trend_faults
from app.trends.mock_trends import slice_for_source


class MockTrendClient:
    mode = "MOCK"

    def fetch(self, source_id: str, *, country: str, language: str, limit: int) -> list[RawTrend]:
        trend_faults.maybe_raise(source_id)
        return slice_for_source(source_id, country=country, language=language, limit=limit)

    def search(self, source_id: str, query: str, *, country: str, language: str) -> list[RawTrend]:
        trend_faults.maybe_raise(source_id)
        base = slice_for_source(source_id, country=country, language=language, limit=6)
        return [t.model_copy(update={"raw_topic": f"{query} — {t.raw_topic}"}) for t in base[:3]]


class HttpTrendClient:
    """Real client placeholder — raises until per-source credentials + adapters
    are wired. Never fabricates trend data."""

    mode = "REAL"

    def fetch(self, *_a, **_k):
        raise TrendError("real trend client not configured — credentials + adapter required",
                         error_type="PERMISSION_MISSING")

    search = fetch


def _client():
    settings = get_settings()
    return HttpTrendClient() if not settings.mock_mode else MockTrendClient()


class BaseTrendProvider:
    source_id = "generic"

    def __init__(self, client=None):
        self.client = client or _client()
        self.provider_mode = self.client.mode
        self.cap = get_trend_capability(self.source_id)

    def get_capabilities(self) -> dict:
        return {
            "source_id": self.source_id, "name": self.cap.name,
            "source_type": self.cap.source_type, "auth_status": self.cap.auth_status,
            "reliability": self.cap.reliability, "freshness": self.cap.freshness,
            "known_limitations": self.cap.known_limitations,
            "provider_mode": self.provider_mode,
        }

    def _gate(self) -> None:
        # OWN_ANALYTICS is AVAILABLE; everything else needs auth/approval we don't
        # have -> in mock mode we still return synthetic data, but the source's
        # auth_status is surfaced honestly and real client raises.
        if self.provider_mode == "REAL" and self.cap.auth_status != "AVAILABLE":
            raise TrendError(f"{self.source_id}: {self.cap.auth_status}",
                             error_type="PERMISSION_MISSING")

    def fetch_trending(self, *, country: str, language: str, limit: int) -> list[RawTrend]:
        self._gate()
        return self.client.fetch(self.source_id, country=country, language=language, limit=limit)

    def search_topic(self, query: str, *, country: str, language: str) -> list[RawTrend]:
        self._gate()
        return self.client.search(self.source_id, query, country=country, language=language)

    def get_topic_history(self, topic: str) -> dict:
        return {"source_id": self.source_id, "topic": topic, "history": "mock"}

    def get_velocity_data(self, topic: str) -> dict:
        hits = self.client.fetch(self.source_id, country="KR", language="ko", limit=60)
        m = next((h for h in hits if topic in h.raw_topic or h.raw_topic in topic), None)
        return m.interest_series if m else {}

    def get_source_metadata(self) -> dict:
        return {"source_id": self.source_id, "auth_status": self.cap.auth_status,
                "last_verified_at": self.cap.last_verified_at}


class YouTubeTrendProvider(BaseTrendProvider):
    source_id = "youtube_most_popular"


class GoogleTrendProvider(BaseTrendProvider):
    source_id = "google_trends"


class WebSearchTrendProvider(BaseTrendProvider):
    source_id = "web_search"


class NewsTrendProvider(BaseTrendProvider):
    source_id = "news_search"


class NaverTrendProvider(BaseTrendProvider):
    source_id = "naver_datalab"


class RedditTrendProvider(BaseTrendProvider):
    source_id = "reddit_signal"


class OwnAnalyticsTrendProvider(BaseTrendProvider):
    source_id = "own_analytics"

    def fetch_trending(self, *, country: str, language: str, limit: int) -> list[RawTrend]:
        """Evergreen / historical-performance topics from OUR data (always available)."""
        from app.db.base import session_scope
        from app.db.models import ContentFeature

        out: list[RawTrend] = []
        seen: set[str] = set()
        with session_scope() as s:
            for cf in (s.query(ContentFeature)
                       .order_by(ContentFeature.created_at.desc()).limit(200)):
                key = cf.topic_cluster or cf.topic
                if key in seen:
                    continue
                seen.add(key)
                out.append(RawTrend(
                    source_id=self.source_id, raw_topic=cf.topic or key, title=cf.topic or key,
                    description="과거 우리 채널에서 다룬 주제 (evergreen 후보)",
                    country=country, language=language,
                    interest_series={"1h": 0.4, "6h": 0.4, "24h": 0.4, "3d": 0.4, "7d": 0.41, "30d": 0.4},
                    engagement_signals={"cluster_hint": cf.topic_cluster, "shape": "evergreen",
                                        "risk_hint": "LOW", "competition_hint": "mid",
                                        "evergreen": True, "own_history": True},
                    reliability="own", raw_payload={"content_id": cf.content_id},
                ))
        return out[: max(1, limit)] or slice_for_source(self.source_id, country=country,
                                                        language=language, limit=min(limit, 6))


class TikTokTrendProvider(BaseTrendProvider):
    source_id = "tiktok_trends"


class ThreadsTrendProvider(BaseTrendProvider):
    source_id = "threads_trends"


class XTrendProvider(BaseTrendProvider):
    source_id = "x_trends"
