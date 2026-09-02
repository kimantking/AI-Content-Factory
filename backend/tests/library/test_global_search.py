"""AUDIT-P8-003 — unified global search across campaigns / platform content /
channels / brands / references / publications."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.db.base import session_scope
from app.db.models import Campaign, PlatformContent, Script
from app.db.models_learn import ReferenceSource
from app.db.models_mb import Brand, Channel, Workspace
from app.library.search import global_search
from app.main import app

client = TestClient(app)


def _seed(ws):
    with session_scope() as db:
        db.add(Workspace(id=ws, name=f"WS {ws[:6]}", slug=f"ws-{ws[:8]}"))
        db.flush()
        c1 = Campaign(id=str(uuid.uuid4()), topic="번역가의 미래와 AI", audience_goal="BALANCED",
                      platforms=["youtube_shorts"], status="SUCCESS", workspace_id=ws)
        c2 = Campaign(id=str(uuid.uuid4()), topic="완전히 다른 주제", audience_goal="BALANCED",
                      platforms=["tiktok"], status="SUCCESS", workspace_id=ws)
        db.add_all([c1, c2])
        db.flush()
        db.add(Script(campaign_id=c2.id, platform="MASTER", body="본문에 번역가 키워드가 들어있다", word_count=5))
        db.add(PlatformContent(campaign_id=c1.id, platform="youtube_shorts", content_type="short",
                               title="AI 번역 도구 정리", caption="cap"))
        b = Brand(id=str(uuid.uuid4()), workspace_id=ws, name="번역 브랜드", slug="translate-brand")
        db.add(b)
        db.flush()
        db.add(Channel(id=str(uuid.uuid4()), workspace_id=ws, brand_id=b.id, name="번역 채널",
                       platform="youtube", channel_type="YOUTUBE_SHORTS"))
        db.add(ReferenceSource(id=str(uuid.uuid4()), workspace_id=ws,
                               url="https://example.com/translation-report",
                               title="번역 산업 리포트 2026", source_type="NEWS_ARTICLE", status="READY"))
        return c1.id, c2.id


def test_search_spans_all_entity_kinds():
    ws = str(uuid.uuid4())
    c1, c2 = _seed(ws)
    with session_scope() as db:
        out = global_search(db, q="번역", workspace_id=ws, limit=30)
    kinds = {r["kind"] for r in out["results"]}
    assert {"campaign", "platform_content", "channel", "brand", "reference"} <= kinds
    # c2 matched only via script body
    assert any(r["kind"] == "campaign" and r["id"] == c2 and "본문" in r["subtitle"]
               for r in out["results"])


def test_search_is_workspace_scoped():
    ws_a, ws_b = str(uuid.uuid4()), str(uuid.uuid4())
    _seed(ws_a)
    with session_scope() as db:
        out = global_search(db, q="번역", workspace_id=ws_b, limit=30)
    assert out["count"] == 0


def test_search_ranking_prefers_exact_and_prefix():
    ws = str(uuid.uuid4())
    _seed(ws)
    with session_scope() as db:
        out = global_search(db, q="번역 브랜드", workspace_id=ws, limit=30)
    assert out["results"][0]["kind"] == "brand"          # exact title match ranks first
    assert out["results"][0]["score"] >= 0.85


def test_search_endpoint_and_kind_filter():
    ws = str(uuid.uuid4())
    _seed(ws)
    r = client.get("/api/search", params={"q": "번역", "workspace_id": ws, "kinds": "brand,channel"})
    assert r.status_code == 200
    body = r.json()
    assert set(body["by_kind"]) <= {"brand", "channel"}
    assert body["count"] >= 2


def test_short_query_rejected():
    with session_scope() as db:
        out = global_search(db, q="a", workspace_id=None)
    assert out["count"] == 0 and "too short" in out["note"]
