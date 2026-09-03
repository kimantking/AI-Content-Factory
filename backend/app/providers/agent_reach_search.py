"""Read-only research adapter powered by Agent Reach's safe upstream tools.

Agent Reach is an installer/router rather than a search wrapper.  This adapter
therefore calls the installed Python upstreams directly: yt-dlp for YouTube and
feedparser for Google News RSS, plus GitHub's public read-only search endpoint.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from app.providers.base import SearchProvider, SearchResultItem
from app.providers.errors import ProviderError


class AgentReachSearchProvider:
    name = "agent_reach"

    def __init__(self, fallback: SearchProvider | None = None):
        self._fallback = fallback

    @staticmethod
    def _youtube(query: str, limit: int) -> list[SearchResultItem]:
        from yt_dlp import YoutubeDL

        options = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "extract_flat": True, "socket_timeout": 12,
        }
        with YoutubeDL(options) as ydl:
            data = ydl.extract_info(f"ytsearch{limit}:{query}", download=False) or {}
        out = []
        for row in data.get("entries") or []:
            video_id = row.get("id")
            url = row.get("webpage_url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else "")
            if url:
                out.append(SearchResultItem(url=url, title=row.get("title") or "YouTube 영상",
                                            snippet=(row.get("description") or "")[:900],
                                            published_at=row.get("upload_date")))
        return out

    @staticmethod
    def _news(query: str, limit: int) -> list[SearchResultItem]:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Content-Factory/1.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(1_500_000)
        import feedparser

        feed = feedparser.loads(raw)
        return [SearchResultItem(url=row.get("link") or "", title=row.get("title") or "뉴스",
                                 snippet=(row.get("summary") or "")[:900],
                                 published_at=row.get("published"))
                for row in (feed.entries or [])[:limit] if row.get("link")]

    @staticmethod
    def _github(query: str, limit: int) -> list[SearchResultItem]:
        url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
            {"q": query, "sort": "updated", "order": "desc", "per_page": limit})
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json", "User-Agent": "AI-Content-Factory/1.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read(1_500_000).decode("utf-8"))
        return [SearchResultItem(url=row.get("html_url") or "", title=row.get("full_name") or "GitHub",
                                 snippet=(row.get("description") or "")[:900],
                                 published_at=row.get("updated_at"))
                for row in data.get("items", [])[:limit] if row.get("html_url")]

    def search(self, query: str, *, max_results: int = 6) -> list[SearchResultItem]:
        limit = max(1, min(max_results, 10))
        per_channel = max(2, (limit + 2) // 3)
        collectors = (self._news, self._youtube, self._github)
        rows: list[SearchResultItem] = []
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="agent-reach") as pool:
            futures = [pool.submit(fn, query, per_channel) for fn in collectors]
            for future in futures:
                try:
                    rows.extend(future.result(timeout=18))
                except Exception:  # one channel must not cancel the other read-only channels
                    continue

        unique: list[SearchResultItem] = []
        seen: set[str] = set()
        for row in rows:
            if row.url and row.url not in seen:
                seen.add(row.url)
                unique.append(row)
            if len(unique) >= limit:
                break
        if len(unique) < 2 and self._fallback is not None:
            try:
                for row in self._fallback.search(query, max_results=limit):
                    if row.url and row.url not in seen:
                        seen.add(row.url)
                        unique.append(row)
                    if len(unique) >= limit:
                        break
            except ProviderError:
                pass
        if not unique:
            raise ProviderError("Agent Reach channels returned no usable sources")
        return unique[:limit]
