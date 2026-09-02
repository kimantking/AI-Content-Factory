from __future__ import annotations

import hashlib

from app.providers.base import SearchResultItem
from app.providers.faults import faults


class MockSearchProvider:
    """Deterministic offline search stand-in (explicit MOCK MODE)."""

    name = "mock"

    def search(self, query: str, *, max_results: int = 6) -> list[SearchResultItem]:
        faults.maybe_raise("search")
        h = hashlib.sha256(query.encode("utf-8")).hexdigest()
        out: list[SearchResultItem] = []
        for i in range(max_results):
            tag = h[i * 4 : i * 4 + 6]
            out.append(
                SearchResultItem(
                    url=f"https://example.org/{tag}",
                    title=f"[{query}] 참고자료 {i + 1}",
                    snippet=(
                        f"'{query}'에 대한 개요와 최근 동향을 다룬 자료 {i + 1}. "
                        f"주요 수치와 사례, 반론을 함께 정리함."
                    ),
                    published_at=f"2026-0{(i % 8) + 1}-15",
                )
            )
        return out
