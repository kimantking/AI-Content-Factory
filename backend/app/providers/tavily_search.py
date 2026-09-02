from __future__ import annotations

from app.providers.base import SearchResultItem
from app.providers.errors import ProviderError, RateLimitError


class TavilySearchProvider:
    """Real adapter. Only used when SEARCH_PROVIDER=tavily and a key is set."""

    name = "tavily"

    def __init__(self, api_key: str):
        try:
            from tavily import TavilyClient  # noqa: PLC0415
        except ImportError as e:  # pragma: no cover
            raise ProviderError(f"tavily-python not installed: {e}") from e
        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, *, max_results: int = 6) -> list[SearchResultItem]:
        try:
            res = self._client.search(query=query, max_results=max_results, search_depth="advanced")
        except Exception as e:  # pragma: no cover - network
            if "rate" in type(e).__name__.lower():
                raise RateLimitError(str(e)) from e
            raise ProviderError(str(e)) from e
        out: list[SearchResultItem] = []
        for r in res.get("results", []):
            out.append(
                SearchResultItem(
                    url=r.get("url", ""),
                    title=r.get("title", ""),
                    snippet=r.get("content", ""),
                    published_at=r.get("published_date"),
                )
            )
        return out
