from __future__ import annotations

import threading
import time
from collections import defaultdict

# Tiny in-process metrics registry with a Prometheus text exposition. No external
# dependency. Counters + gauges + histograms (fixed buckets).

_lock = threading.Lock()
_counters: dict[tuple[str, tuple], float] = defaultdict(float)
_gauges: dict[tuple[str, tuple], float] = {}
_hist_buckets = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)
_hist: dict[tuple[str, tuple], dict] = {}
_help: dict[str, str] = {}


def _key(labels: dict | None) -> tuple:
    return tuple(sorted((labels or {}).items()))


def counter(name: str, value: float = 1.0, labels: dict | None = None, help: str = "") -> None:
    with _lock:
        _counters[(name, _key(labels))] += value
        if help:
            _help[name] = help


def gauge(name: str, value: float, labels: dict | None = None, help: str = "") -> None:
    with _lock:
        _gauges[(name, _key(labels))] = value
        if help:
            _help[name] = help


def observe(name: str, seconds: float, labels: dict | None = None, help: str = "") -> None:
    k = (name, _key(labels))
    with _lock:
        h = _hist.get(k)
        if h is None:
            h = {"sum": 0.0, "count": 0, "buckets": {b: 0 for b in _hist_buckets}}
            _hist[k] = h
        h["sum"] += seconds
        h["count"] += 1
        for b in _hist_buckets:
            if seconds <= b:
                h["buckets"][b] += 1
        if help:
            _help[name] = help


class timer:
    def __init__(self, name: str, labels: dict | None = None):
        self.name, self.labels = name, labels

    def __enter__(self):
        self._t = time.perf_counter()
        return self

    def __exit__(self, *a):
        observe(self.name, time.perf_counter() - self._t, self.labels)
        return False


def _fmt_labels(lbls: tuple, extra: tuple | None = None) -> str:
    items = list(lbls) + (list(extra) if extra else [])
    if not items:
        return ""
    return "{" + ",".join(f'{k}="{v}"' for k, v in items) + "}"


def render_prometheus() -> str:
    """Snapshot + include a few live gauges (DB pool, queue depth)."""
    _refresh_live_gauges()
    lines: list[str] = []
    with _lock:
        emitted: set[str] = set()

        def head(name, typ):
            if name in emitted:
                return
            emitted.add(name)
            if name in _help:
                lines.append(f"# HELP {name} {_help[name]}")
            lines.append(f"# TYPE {name} {typ}")

        for (name, lbls), v in sorted(_counters.items()):
            head(name, "counter")
            lines.append(f"{name}{_fmt_labels(lbls)} {v}")
        for (name, lbls), v in sorted(_gauges.items()):
            head(name, "gauge")
            lines.append(f"{name}{_fmt_labels(lbls)} {v}")
        for (name, lbls), h in sorted(_hist.items()):
            head(name, "histogram")
            acc = 0
            for b in _hist_buckets:
                acc = h["buckets"][b]
                lines.append(f'{name}_bucket{_fmt_labels(lbls, (("le", b),))} {acc}')
            lines.append(f'{name}_bucket{_fmt_labels(lbls, (("le", "+Inf"),))} {h["count"]}')
            lines.append(f"{name}_sum{_fmt_labels(lbls)} {h['sum']}")
            lines.append(f"{name}_count{_fmt_labels(lbls)} {h['count']}")
    return "\n".join(lines) + "\n"


def _refresh_live_gauges() -> None:
    try:
        from app.db.base import engine

        pool = engine.pool
        gauge("acf_db_pool_checkedout", pool.checkedout(), help="DB connections in use")
        gauge("acf_db_pool_size", pool.size(), help="DB pool size")
    except Exception:  # noqa: BLE001
        pass
    try:
        import redis

        from app.config import get_settings

        r = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        for q in ("celery", "image", "video", "audio", "render", "publish", "analytics", "autopilot"):
            gauge("acf_queue_depth", r.llen(q), {"queue": q}, help="pending jobs per queue")
    except Exception:  # noqa: BLE001
        pass


def reset_for_tests() -> None:
    with _lock:
        _counters.clear()
        _gauges.clear()
        _hist.clear()
