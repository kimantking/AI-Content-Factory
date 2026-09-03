from __future__ import annotations

from app.providers.agent_reach_search import AgentReachSearchProvider
from app.providers.base import SearchResultItem


def _row(url: str, title: str) -> SearchResultItem:
    return SearchResultItem(url=url, title=title, snippet="verified")


def test_agent_reach_merges_read_only_channels_and_deduplicates(monkeypatch):
    monkeypatch.setattr(AgentReachSearchProvider, "_news",
                        staticmethod(lambda _q, _n: [_row("https://news.example/a", "뉴스")]))
    monkeypatch.setattr(AgentReachSearchProvider, "_youtube",
                        staticmethod(lambda _q, _n: [_row("https://youtube.com/watch?v=1", "영상")]))
    monkeypatch.setattr(AgentReachSearchProvider, "_github",
                        staticmethod(lambda _q, _n: [_row("https://news.example/a", "중복"),
                                                    _row("https://github.com/o/r", "저장소")]))

    rows = AgentReachSearchProvider().search("AI 영상", max_results=6)
    assert [row.url for row in rows] == [
        "https://news.example/a", "https://youtube.com/watch?v=1", "https://github.com/o/r"]


def test_agent_reach_uses_tavily_only_when_core_channels_fail(monkeypatch):
    for name in ("_news", "_youtube", "_github"):
        monkeypatch.setattr(AgentReachSearchProvider, name,
                            staticmethod(lambda _q, _n: []))

    class Fallback:
        name = "tavily"

        def search(self, _query: str, *, max_results: int = 6):
            return [_row("https://fallback.example/a", "보조 출처")]

    rows = AgentReachSearchProvider(fallback=Fallback()).search("AI", max_results=6)
    assert rows[0].url == "https://fallback.example/a"
