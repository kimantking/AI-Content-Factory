"""Phase 9 — real-world validation helpers: a metrics recorder, a concurrent
campaign runner, and DB/pool observation. All load runs use mock providers +
local Ollama + deterministic fixtures (no paid calls)."""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import pytest

from app.db.base import engine, session_scope
from app.db.models import Campaign


@dataclass
class TierMetrics:
    name: str
    started_at: float = 0.0
    finished_at: float = 0.0
    items: int = 0
    ok: int = 0
    failed: int = 0
    extra: dict = field(default_factory=dict)

    def start(self, items: int) -> "TierMetrics":
        self.started_at = time.time()
        self.items = items
        return self

    def done(self) -> "TierMetrics":
        self.finished_at = time.time()
        return self

    @property
    def duration(self) -> float:
        return round((self.finished_at or time.time()) - self.started_at, 2)

    def as_dict(self) -> dict:
        return {"tier": self.name, "duration_s": self.duration, "items": self.items,
                "ok": self.ok, "failed": self.failed, **self.extra}


@pytest.fixture
def metrics():
    recorded: list[dict] = []

    def _mk(name: str) -> TierMetrics:
        return TierMetrics(name)

    _mk.recorded = recorded  # type: ignore[attr-defined]
    return _mk


def pool_status() -> dict:
    p = engine.pool
    return {
        "size": p.size(), "checked_in": p.checkedin(), "checked_out": p.checkedout(),
        "overflow": p.overflow(),
    }


def new_campaign(topic: str = "동시성 테스트 주제", *, goal: str = "BALANCED",
                 platforms=None, workspace_id=None, brand_id=None,
                 channel_id=None, execution_mode=None) -> str:
    cid = str(uuid.uuid4())
    with session_scope() as s:
        s.add(Campaign(id=cid, topic=topic, audience_goal=goal,
                       platforms=platforms or ["youtube_shorts"], status="WAITING",
                       workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id,
                       execution_mode=execution_mode))
    return cid


def run_one_campaign(cid: str, topic: str, platforms=None) -> dict:
    """Run one Phase 1-A pipeline; return {cid, status, error, seconds}."""
    from app.agents.runner import run_pipeline

    t0 = time.time()
    try:
        st = run_pipeline(cid, topic, "BALANCED", platforms or ["youtube_shorts"])
        return {"cid": cid, "status": st.get("status"), "error": None,
                "seconds": round(time.time() - t0, 2)}
    except Exception as e:  # noqa: BLE001 — a load run records failures, doesn't abort
        return {"cid": cid, "status": "EXCEPTION", "error": f"{type(e).__name__}: {e}",
                "seconds": round(time.time() - t0, 2)}


def run_campaigns_concurrent(n: int, *, workers: int, topic_prefix="load") -> dict:
    """Fire n pipelines across a thread pool; collect per-campaign result + pool
    high-water mark. Deterministic mock providers -> no paid calls."""
    cids = [(new_campaign(f"{topic_prefix} 캠페인 {i}"), f"{topic_prefix} 캠페인 {i}")
            for i in range(n)]
    hw = {"checked_out": 0, "overflow": 0}
    results: list[dict] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(run_one_campaign, cid, topic): cid for cid, topic in cids}
        for f in as_completed(futs):
            results.append(f.result())
            ps = pool_status()
            hw["checked_out"] = max(hw["checked_out"], ps["checked_out"])
            hw["overflow"] = max(hw["overflow"], ps["overflow"])
    ok = sum(1 for r in results if r["status"] == "SUCCESS")
    return {
        "n": n, "workers": workers, "ok": ok, "failed": n - ok,
        "wall_s": round(time.time() - t0, 2),
        "latency_p50": _pct([r["seconds"] for r in results], 50),
        "latency_max": max((r["seconds"] for r in results), default=0),
        "pool_high_water": hw,
        "results": results,
    }


def _pct(xs: list[float], p: int) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, round((p / 100) * (len(xs) - 1))))
    return xs[k]


def ollama_reachable() -> bool:
    import urllib.request

    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3).read()
        return True
    except Exception:  # noqa: BLE001
        return False
