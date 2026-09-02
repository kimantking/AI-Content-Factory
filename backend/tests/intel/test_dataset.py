"""§AD-§AH — Dataset Engine, quality scoring, deduplication, DataCurator."""
from __future__ import annotations

from app.db.base import session_scope
from app.db.models_learn import DatasetRecord, ReferenceSource
from app.intel.dataset import active_records, curate
from app.intel.engine import add_urls, run_learning_job
from app.intel.quality import (
    analyze_quality,
    content_hash,
    duplicate_of,
    freshness,
    text_fingerprint,
)


def test_quality_scores_have_components_and_weight():
    doc = {"main_text": "연구에 따르면 자동화율이 40% 늘었다. " * 20, "title": "자동화 보고서",
           "published_at": "2026-05-01", "author": "연구팀", "headings": ["개요"],
           "source_references": [{"href": "https://x.org/report"}]}
    qs = analyze_quality(doc, source_type="OFFICIAL_DOCUMENT", topic="자동화")
    for k in ("source_quality", "information_density", "relevance", "novelty",
              "freshness", "noise", "aggregate", "learning_weight"):
        assert 0.0 <= qs[k] <= 1.0
    assert qs["source_quality"] >= 0.8       # official doc
    assert qs["low_value"] is False


def test_injection_severity_penalizes_quality():
    doc = {"main_text": "짧은 본문. " * 10, "title": "t", "headings": []}
    clean = analyze_quality(doc, source_type="BLOG", topic="x", injection_severity="NONE")
    poisoned = analyze_quality(doc, source_type="BLOG", topic="x", injection_severity="HIGH")
    assert poisoned["aggregate"] < clean["aggregate"]


def test_freshness_unknown_is_neutral_not_zero():
    assert freshness("") == 0.5
    assert freshness("2019-01-01") < freshness("2026-01-01")


def test_dedup_methods():
    long_text = " ".join(
        f"{i}번째 문단에서는 자동화 비율과 검수 인력의 관계를 사례 중심으로 설명한다." for i in range(40))
    existing = [{"id": "r1", "canonical_url": "https://x.com/a",
                 "content_hash": content_hash(long_text),
                 "text_fingerprint": text_fingerprint(long_text),
                 "sim_vector": [], "main_text": long_text}]
    # same content, different tracking url + trailing punctuation -> normalised hash match
    assert duplicate_of({"main_text": long_text + "  "}, canonical_url="https://x.com/b",
                        existing=existing)["method"] == "content_hash"
    # canonical url match
    assert duplicate_of({"main_text": "무관한 텍스트"}, canonical_url="https://x.com/a",
                        existing=existing)["method"] == "canonical_url"
    # a few words changed in a long article -> fingerprint / similarity match
    near = long_text.replace("사례 중심으로", "데이터 중심으로").replace("39번째", "40번째")
    hit = duplicate_of({"main_text": near}, canonical_url="https://x.com/c", existing=existing)
    assert hit and hit["method"] in ("text_fingerprint", "text_similarity", "semantic")
    # a genuinely different article
    other = " ".join(f"{i}번째 항목은 반려동물 사료 시장의 계절성에 대한 것이다." for i in range(40))
    assert duplicate_of({"main_text": other}, canonical_url="https://x.com/d", existing=existing) is None


def test_learning_run_writes_dataset_records_and_curates(tenant):
    ws = tenant["workspace_id"]
    urls = [f"https://batch.example.com/a{i}" for i in range(10)]
    with session_scope() as db:
        job = add_urls(db, urls=urls, execution_mode="LEARN_ONLY", workspace_id=ws, topic="자동화")
        jid = job.id
    with session_scope() as db:
        res = run_learning_job(db, jid)
    assert res["datasets"] > 0
    with session_scope() as db:
        recs = active_records(db, workspace_id=ws)
        assert recs
        assert all(r.content_hash for r in recs)
        # a second curate pass is idempotent-ish and reports stats
        stats = curate(db, workspace_id=ws)
        assert stats["scanned"] >= len(recs)


def test_curator_deactivates_rights_problem_records(tenant):
    ws = tenant["workspace_id"]
    with session_scope() as db:
        db.add(DatasetRecord(workspace_id=ws, dataset_type="FACT_DATASET",
                             content_hash="h1", payload={"claims": ["x"]},
                             quality_score=0.7, rights_status="UNKNOWN_RIGHTS", active=True))
        db.add(DatasetRecord(workspace_id=ws, dataset_type="FACT_DATASET",
                             content_hash="h2", payload={"claims": ["y"]},
                             quality_score=0.7, rights_status="RESEARCH_REFERENCE", active=True))
    with session_scope() as db:
        stats = curate(db, workspace_id=ws)
        assert stats["rights_problem"] >= 1
        rows = {r.content_hash: r.active for r in db.query(DatasetRecord).filter_by(workspace_id=ws)}
        assert rows["h1"] is False and rows["h2"] is True
