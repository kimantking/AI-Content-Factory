from __future__ import annotations

import hashlib

from app.media.draw import placeholder_card
from app.providers.faults import faults
from app.providers.media.base import StockItem
from app.schemas.media import ProviderMode


def semantic_relevance(query: str, tags: str) -> float:
    """Cheap lexical overlap stand-in for a real embedding similarity."""
    q = {t for t in query.lower().split() if len(t) > 1}
    t = {t for t in tags.lower().split() if len(t) > 1}
    if not q:
        return 0.0
    return round(len(q & t) / len(q), 3)


class MockStockProvider:
    name = "mock-stock"
    mode = ProviderMode.MOCK

    def search(self, *, query: str, width: int, height: int, want_video: bool,
               out_path: str) -> StockItem:
        faults.maybe_raise("stock", "media")
        # deterministic "closest clip" — reuse the query as its own tags so
        # relevance is high but not blindly 1.0
        h = hashlib.sha256(query.encode()).hexdigest()[:6]
        tags = query + " broll footage"
        img = placeholder_card(width, height, title=f"STOCK · {query[:40]}",
                               subtitle=f"clip {h}", seed=h, watermark="MOCK STOCK")
        img.save(out_path, "PNG")
        return StockItem(
            path=out_path, title=f"stock:{query[:40]}", provider=self.name,
            provider_mode=self.mode,
            semantic_relevance_score=max(0.55, semantic_relevance(query, tags)),
            width=width, height=height, duration=None, cost=0.0,
        )
