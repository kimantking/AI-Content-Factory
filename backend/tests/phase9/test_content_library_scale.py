"""Phase 9 §55-§58 — Content Library at real-world scale: 1000+ campaigns,
3000+ platform contents, legacy + current mixed. Pagination / search / filter
stay bounded (no full preload), no crash."""
from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.base import engine, session_scope
from app.db.models import Campaign, PlatformContent, Script
from app.main import app

pytestmark = [pytest.mark.phase9, pytest.mark.load]
client = TestClient(app, raise_server_exceptions=False)

N_CAMPAIGNS = 1000
N_CONTENTS = 3200


@pytest.fixture
def big_library():
    ws = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.exec_driver_sql("SET session_replication_role = replica")   # speed: skip FK checks for the bulk insert
    with session_scope() as db:
        camps, scripts, contents = [], [], []
        for i in range(N_CAMPAIGNS):
            cid = str(uuid.uuid4())
            legacy = i % 5 == 0
            camps.append(Campaign(
                id=cid, topic=f"대량 라이브러리 캠페인 {i} — 번역과 자동화" if i % 7 == 0
                else f"대량 캠페인 {i}", audience_goal="BALANCED",
                platforms=["youtube_shorts", "tiktok"], status="SUCCESS" if i % 3 else "FAILED",
                workspace_id=None if legacy else ws,
                execution_mode=None if legacy else "CREATE_AND_LEARN"))
            scripts.append(Script(campaign_id=cid, platform="MASTER",
                                  body=f"본문 {i} 자동화 키워드", word_count=3, qa_passed=True))
            for k in range(N_CONTENTS // N_CAMPAIGNS + (1 if i < N_CONTENTS % N_CAMPAIGNS else 0)):
                contents.append(PlatformContent(
                    campaign_id=cid, platform=("youtube_shorts" if k == 0 else "tiktok"),
                    content_type="short", title=f"콘텐츠 {i}-{k}"))
        db.bulk_save_objects(camps)
        db.bulk_save_objects(scripts)
        db.bulk_save_objects(contents)
    with engine.begin() as conn:
        conn.exec_driver_sql("SET session_replication_role = origin")
    return ws


def test_pagination_is_bounded_and_fast(big_library):
    t0 = time.time()
    r = client.get("/api/library", params={"page": 1, "page_size": 30})
    dt = time.time() - t0
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) <= 30, "page returned more than page_size (full preload?)"
    assert body.get("total", body.get("count", 0)) >= N_CAMPAIGNS
    assert dt < 8.0, f"first page took {dt:.1f}s at {N_CAMPAIGNS} campaigns"
    # a deep page still works
    r2 = client.get("/api/library", params={"page": 20, "page_size": 30})
    assert r2.status_code == 200 and len(r2.json()["items"]) <= 30


def test_search_and_filter_at_scale(big_library):
    r = client.get("/api/library", params={"q": "번역", "page_size": 30})
    assert r.status_code == 200
    assert 0 < len(r.json()["items"]) <= 30
    r2 = client.get("/api/library", params={"status": "FAILED", "page_size": 30})
    assert r2.status_code == 200
    assert all(c["status"] == "FAILED" for c in r2.json()["items"])
    # global search endpoint also bounded
    g = client.get("/api/search", params={"q": "자동화", "limit": 20})
    assert g.status_code == 200 and len(g.json()["results"]) <= 20


def test_legacy_and_current_mixed_no_crash(big_library):
    r = client.get("/api/library", params={"page_size": 50})
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(c.get("legacy") for c in items) and any(not c.get("legacy") for c in items)
    # opening a legacy campaign detail does not 500
    legacy = next(c for c in items if c.get("legacy"))
    assert client.get(f"/api/library/{legacy['campaign_id']}").status_code == 200


def test_library_stats_bounded(big_library):
    t0 = time.time()
    r = client.get("/api/library/stats")
    assert r.status_code == 200
    assert time.time() - t0 < 8.0
