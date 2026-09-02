"""Phase 9 §14-§17 — LEARN_ONLY batch load (10 / 50 / 100 references).

Invariants under load: LEARN_ONLY produces ZERO campaign / media / render /
publish rows. Cheap-first: deep analysis is bounded to top-K (deterministic
analyzers — 0 premium LLM calls for the whole batch). Dedup: repeated / canonical
/ same-hash URLs do not explode the dataset."""
from __future__ import annotations

import time
import uuid

import pytest

from app.db.base import session_scope
from app.db.models import Asset, Campaign, MediaTask, PublishJob
from app.db.models_learn import DatasetRecord, LearningJob, ReferenceAnalysis, ReferenceSource
from app.intel import fetch as _fetch
from app.intel.engine import add_urls, run_learning_job

pytestmark = [pytest.mark.phase9, pytest.mark.load]

_REPORT: list[dict] = []


def _html(i: int) -> str:
    return f"""<html><head><title>배치 학습 기사 {i}</title>
<meta name="author" content="기자{i}"><meta property="og:site_name" content="미디어랩">
<meta property="article:published_time" content="2026-07-1{i % 9}"></head><body>
<main><h1>배치 학습 기사 {i}</h1>
<p>연구에 따르면 자동화 비율이 2026년 기준 {30 + i % 40}% 로 상승했다는 조사가 있다.</p>
<p>전문가 {i}는 사람의 검수·판단 역할이 커진다고 말했다.</p>
<p>예를 들어 사례 {i}에서는 초벌 자동화 후 사람이 사실 확인을 담당한다.</p>
<p>다만 저작권과 맥락 판단은 여전히 사람의 몫으로 남는다.</p>
<p>설문에서 응답자 {50 + i % 40}%가 보조 도구를 주 3회 이상 쓴다고 답했다.</p>
</main></body></html>"""


@pytest.fixture
def mock_refs(n_urls=140):
    c = _fetch.MockReferenceClient()
    for i in range(n_urls):
        c.register(f"https://batch.example.com/a{i}", body=_html(i))
    # dedup fixtures
    c.register("https://batch.example.com/a0/", body=_html(0))          # trailing-slash variant
    c.register("https://batch.example.com/dup", body=_html(0))          # identical content
    _fetch.set_client(c)
    yield c
    _fetch.set_client(_fetch.MockReferenceClient())


def _production_footprint(ws: str) -> dict:
    with session_scope() as db:
        return {
            "campaigns": db.query(Campaign).filter_by(workspace_id=ws).count(),
            "assets": db.query(Asset).join(Campaign, Asset.campaign_id == Campaign.id)
                        .filter(Campaign.workspace_id == ws).count(),
            "media_tasks": db.query(MediaTask).join(Campaign, MediaTask.campaign_id == Campaign.id)
                        .filter(Campaign.workspace_id == ws).count(),
            "publish_jobs": db.query(PublishJob).join(Campaign, PublishJob.campaign_id == Campaign.id)
                        .filter(Campaign.workspace_id == ws).count(),
        }


@pytest.mark.parametrize("n", [10, 50, 100])
def test_learn_only_batch(n, mock_refs):
    ws = str(uuid.uuid4())
    urls = [f"https://batch.example.com/a{i}" for i in range(n)]
    t0 = time.time()
    with session_scope() as db:
        job = add_urls(db, urls=urls, execution_mode="LEARN_ONLY", workspace_id=ws,
                       topic="AI와 콘텐츠 제작")
        jid = job.id
    with session_scope() as db:
        res = run_learning_job(db, jid)
    dur = round(time.time() - t0, 2)

    with session_scope() as db:
        refs = db.query(ReferenceSource).filter_by(learning_job_id=jid).count()
        rows = (db.query(ReferenceAnalysis.reference_id, ReferenceAnalysis.analysis_kind)
                .join(ReferenceSource, ReferenceAnalysis.reference_id == ReferenceSource.id)
                .filter(ReferenceSource.learning_job_id == jid).all())
        analyses = len(rows)
        # "deep" = any analysis kind other than the Stage-1 cheap QUALITY row
        deep_refs = len({rid for rid, kind in rows if kind != "QUALITY"})
    fp = _production_footprint(ws)
    _REPORT.append({"n": n, "dur_s": dur, "refs": refs, "analyses": analyses,
                    "deep_refs": deep_refs, "footprint": fp, "res_ok": res.get("ok", True)})

    # ---- LEARN_ONLY invariant: zero production ----
    assert fp == {"campaigns": 0, "assets": 0, "media_tasks": 0, "publish_jobs": 0}, fp
    # ---- cheap-first: deep analysis bounded to top-K, not all N ----
    from app.config import get_settings
    top_k = get_settings().learning_deep_analysis_top_k
    assert deep_refs <= top_k, f"deep-analysed {deep_refs} refs > top_k {top_k}"


def test_learning_dedup_does_not_explode(mock_refs):
    ws = str(uuid.uuid4())
    urls = (["https://batch.example.com/a0"] * 3 +          # exact repeat
            ["https://batch.example.com/a0/",               # canonical variant
             "https://batch.example.com/dup"] +             # same content hash
            [f"https://batch.example.com/a{i}" for i in range(1, 6)])
    with session_scope() as db:
        job = add_urls(db, urls=urls, execution_mode="LEARN_ONLY", workspace_id=ws, topic="t")
        jid = job.id
    with session_scope() as db:
        run_learning_job(db, jid)
        refs = db.query(ReferenceSource).filter_by(learning_job_id=jid).all()
        statuses = [r.status for r in refs]
        datasets = db.query(DatasetRecord).filter_by(workspace_id=ws).count()
    # the 3 identical raw URLs are collapsed at add time; the content-dup is marked
    assert statuses.count("DUPLICATE") >= 1
    # dataset rows stay bounded (roughly the distinct-content count, never 10+)
    assert datasets <= 8, datasets


def test_learning_load_report():
    for r in _REPORT:
        print(f"[LEARN] n={r['n']:>3} dur={r['dur_s']}s refs={r['refs']} "
              f"analyses={r['analyses']} deep_refs={r['deep_refs']} "
              f"production={r['footprint']}")
    assert _REPORT
