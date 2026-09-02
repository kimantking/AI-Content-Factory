"""Phase 9 §86-§90 — QUICK_SOAK. A small workload (campaign + learning + library
reads) repeated for SOAK_SECONDS (default 600) while sampling RSS, DB-pool
checkout, and open file handles. Fails on a clear monotonic upward trend.

Opt-in: marked `soak`; run with `-m soak`. FULL_SOAK is the same test with
SOAK_SECONDS≈2400 (AVAILABLE_NOT_REQUIRED for this gate)."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import gc
import os
import time
import tracemalloc
import uuid

import pytest

from app.db.base import engine, session_scope
from tests.phase9.conftest import new_campaign, pool_status, run_one_campaign

pytestmark = [pytest.mark.phase9, pytest.mark.soak]

SOAK_SECONDS = int(os.environ.get("SOAK_SECONDS", "600"))


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def _rss_mb() -> float:
    """Working-set size via the Win32 API — no third-party dependency."""
    for dll, fn in (("kernel32", "K32GetProcessMemoryInfo"), ("psapi", "GetProcessMemoryInfo")):
        try:
            c = _PMC()
            c.cb = ctypes.sizeof(_PMC)
            h = ctypes.windll.kernel32.GetCurrentProcess()
            if getattr(ctypes.windll, dll)[fn](h, ctypes.byref(c), c.cb):
                return round(c.WorkingSetSize / (1024 * 1024), 1)
        except Exception:  # noqa: BLE001
            continue
    return -1.0


def _fd_count() -> int:
    """Open handle count for this process (Win32)."""
    try:
        n = wt.DWORD()
        ok = ctypes.windll.kernel32.GetProcessHandleCount(
            ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(n))
        return int(n.value) if ok else -1
    except Exception:  # noqa: BLE001
        return -1


def _one_cycle(i: int) -> dict:
    cid = new_campaign(f"soak 캠페인 {i}")
    r = run_one_campaign(cid, f"soak 캠페인 {i}")
    # a learning micro-batch
    from app.intel import fetch as F
    c = F.MockReferenceClient()
    for k in range(3):
        c.register(f"https://soak.example.com/{i}-{k}",
                   body=f"<html><head><title>s{i}{k}</title></head><body><main><h1>s{i}{k}</h1>"
                        f"<p>연구에 따르면 자동화가 {40+k}% 라고 한다. 전문가는 검수가 중요하다 말했다. "
                        f"예시에서 사람이 확인한다.</p></main></body></html>")
    F.set_client(c)
    try:
        from app.intel.engine import add_urls, run_learning_job
        ws = str(uuid.uuid4())
        with session_scope() as db:
            j = add_urls(db, urls=[f"https://soak.example.com/{i}-{k}" for k in range(3)],
                         execution_mode="LEARN_ONLY", workspace_id=ws, topic="soak")
            jid = j.id
        with session_scope() as db:
            run_learning_job(db, jid)
    finally:
        F.set_client(F.MockReferenceClient())
    # a library read
    from app.library.service import list_content
    with session_scope() as db:
        list_content(db, page=1, page_size=30)
    return r


def _trend(xs: list[float]) -> float:
    """Least-squares slope per sample (positive == growing)."""
    n = len(xs)
    if n < 4:
        return 0.0
    mx = (n - 1) / 2
    my = sum(xs) / n
    num = sum((i - mx) * (x - my) for i, x in enumerate(xs))
    den = sum((i - mx) ** 2 for i in range(n))
    return round(num / den, 4) if den else 0.0


def test_quick_soak():
    tracemalloc.start()
    t_end = time.time() + SOAK_SECONDS
    rss, pool_out, fds, heap = [], [], [], []
    cycles = ok = failed = 0
    errors: list[str] = []
    while time.time() < t_end:
        cycles += 1
        try:
            r = _one_cycle(cycles)
            ok += 1 if r["status"] == "SUCCESS" else 0
            failed += 0 if r["status"] == "SUCCESS" else 1
            if r["status"] != "SUCCESS":
                errors.append(f"cycle {cycles}: {r.get('error') or r['status']}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            errors.append(f"cycle {cycles}: {type(e).__name__}: {e}")
        if cycles % 5 == 0:
            gc.collect()
            rss.append(_rss_mb())
            pool_out.append(pool_status()["checked_out"])
            fds.append(_fd_count())
            heap.append(round(tracemalloc.get_traced_memory()[0] / (1024 * 1024), 2))
            print(f"[SOAK] t={int(SOAK_SECONDS - (t_end - time.time()))}s cycle={cycles} "
                  f"ok={ok} failed={failed} rss={rss[-1]}MB heap={heap[-1]}MB "
                  f"pool_out={pool_out[-1]} fd={fds[-1]}")

    tracemalloc.stop()
    rss_slope = _trend([r for r in rss if r >= 0])
    heap_slope = _trend(heap)
    pool_slope = _trend(pool_out)
    fd_slope = _trend([f for f in fds if f >= 0])
    print(f"[SOAK] DONE cycles={cycles} ok={ok} failed={failed} dur={SOAK_SECONDS}s")
    print(f"[SOAK] rss={rss}  heap={heap}  pool_out={pool_out}  fd={fds}")
    print(f"[SOAK] slope_rss={rss_slope}MB/sample slope_heap={heap_slope} "
          f"slope_pool={pool_slope} slope_fd={fd_slope}")

    assert cycles >= 5, "soak did not complete enough cycles"
    assert failed == 0, errors[:5]
    # pool must return to baseline (no leaked connections)
    assert pool_status()["checked_out"] <= 1
    # no runaway growth: flag only a sustained climb, not noise
    if len(rss) >= 4 and rss[0] > 0:
        assert not (rss_slope > 10 and rss[-1] > rss[0] + 80), f"possible RSS leak: {rss}"
    if len(heap) >= 4:
        assert not (heap_slope > 1.0 and heap[-1] > heap[0] + 15), f"possible heap leak: {heap}"
    assert pool_slope <= 0.5, f"pool checkout trending up: {pool_out}"
    if fd_slope and all(f >= 0 for f in fds):
        assert fd_slope < 8, f"handles trending up: {fds}"
