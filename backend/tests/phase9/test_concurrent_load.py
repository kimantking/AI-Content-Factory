"""Phase 9 §10-§13 — concurrent campaign load. Goal: find bottlenecks / races,
not big numbers. Mock providers + local checkpointer -> no paid calls.

Records started/finished/duration/ok/failed + DB-pool high-water mark. The
completion gate is: no data corruption, no crash, bounded resource use, and
every finished campaign is internally consistent (Script row, knowledge_pack,
SUCCESS status all agree)."""
from __future__ import annotations

import pytest

from app.db.base import session_scope
from app.db.models import Campaign, Script
from tests.phase9.conftest import pool_status, run_campaigns_concurrent

pytestmark = [pytest.mark.phase9, pytest.mark.load]

_REPORT: list[dict] = []


def _consistency_check(cids: list[str]) -> list[str]:
    """Return a list of corruption findings (empty == clean)."""
    bad = []
    with session_scope() as db:
        for cid in cids:
            camp = db.get(Campaign, cid)
            if camp is None:
                bad.append(f"{cid}: campaign row vanished")
                continue
            scripts = db.query(Script).filter_by(campaign_id=cid).count()
            if camp.status == "SUCCESS":
                if scripts != 1:
                    bad.append(f"{cid}: SUCCESS but {scripts} scripts")
                if not camp.knowledge_pack:
                    bad.append(f"{cid}: SUCCESS but empty knowledge_pack")
            elif camp.status in ("WAITING", "RUNNING"):
                bad.append(f"{cid}: stuck at {camp.status} after the run returned")
    return bad


@pytest.mark.parametrize("n,workers", [(5, 5), (10, 8), (20, 8)])
def test_concurrent_campaigns(n, workers):
    res = run_campaigns_concurrent(n, workers=workers, topic_prefix=f"load{n}")
    cids = [r["cid"] for r in res["results"]]
    findings = _consistency_check(cids)
    _REPORT.append({"n": n, "workers": workers, "ok": res["ok"], "failed": res["failed"],
                    "wall_s": res["wall_s"], "latency_p50": res["latency_p50"],
                    "latency_max": res["latency_max"], "pool": res["pool_high_water"],
                    "corruption": findings})

    # no partial/corrupt state regardless of pass/fail counts
    assert findings == [], findings
    # the pool must not have leaked connections (checked_out returns to ~0)
    after = pool_status()
    assert after["checked_out"] <= 1, after
    # under mock providers every campaign should actually complete
    assert res["failed"] == 0, [r for r in res["results"] if r["status"] != "SUCCESS"][:3]
    # bounded: pool never exceeded size+overflow
    assert res["pool_high_water"]["overflow"] <= 10, res["pool_high_water"]


def test_report_summary(capsys):
    """Emit the load table so the tier run shows real numbers."""
    for row in _REPORT:
        print(f"[LOAD] n={row['n']:>2} workers={row['workers']} "
              f"ok={row['ok']} failed={row['failed']} wall={row['wall_s']}s "
              f"p50={row['latency_p50']}s max={row['latency_max']}s "
              f"pool_out_hw={row['pool']['checked_out']} overflow_hw={row['pool']['overflow']}")
    assert _REPORT, "load parametrisation did not run"
