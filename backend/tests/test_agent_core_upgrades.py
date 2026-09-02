from __future__ import annotations

from types import SimpleNamespace

from app.agents import factcheck as fc
from app.agents import hooks as hk
from app.agents import research as rs


def _src(url, title="t", snippet="s", pub="2026-01-15"):
    return SimpleNamespace(url=url, title=title, snippet=snippet, published_at=pub)


# ---- Research: query decomposition + ranking ---------------------------- #

def test_expand_queries_is_deterministic_and_topic_first():
    q1 = rs.expand_queries("AI 일자리", ["자동화", "전망"], limit=3)
    q2 = rs.expand_queries("AI 일자리", ["자동화", "전망"], limit=3)
    assert q1 == q2
    assert q1[0] == "AI 일자리"
    assert len(q1) == 3 and len(set(q1)) == 3


def test_merge_and_rank_dedupes_and_prefers_authority_and_diversity():
    gov = _src("https://data.go.kr/report", "정부 통계", "AI 일자리 수치")
    blog = _src("https://someone.tistory.com/1", "블로그 글", "AI 일자리 잡담")
    dupe = _src("https://data.go.kr/report", "dup", "dup")
    news = _src("https://news.example.com/x", "뉴스", "AI 일자리 동향 2026")
    ranked = rs.merge_and_rank([[gov, blog], [dupe, news]], topic="AI 일자리", limit=8)
    urls = [r.url for r in ranked]
    assert urls.count("https://data.go.kr/report") == 1          # dedup
    assert urls[0] == "https://data.go.kr/report"                # authority wins
    assert rs.source_diversity(ranked) >= 0.6


def test_find_contradictions():
    facts = [{"fact": "AI로 번역 일자리가 크게 감소했다"},
             {"fact": "AI로 번역 일자리가 오히려 증가했다"},
             {"fact": "돌봄 노동은 안정적이다"}]
    c = rs.find_contradictions(facts)
    assert c and "번역" in c[0]["shared_terms"] + [w for w in c[0]["shared_terms"]]


def test_coverage_score_range():
    s = rs.coverage_score([{"fact": "a"}, {"fact": "b"}], [_src("https://a.com/1"), _src("https://b.com/2")])
    assert 0.0 <= s <= 1.0


# ---- Fact checker: atomic claims + enrichment ------------------------- #

def test_atomic_claims_splits_compound_but_passes_simple_through():
    facts = [
        {"fact": "번역 수요가 20% 줄었고 통역 수요는 10% 늘었다", "source_ids": ["s1"], "confidence": 0.8},
        {"fact": "돌봄 노동은 자동화가 느리다", "source_ids": ["s2"], "confidence": 0.7},
    ]
    out = fc.atomic_claims(facts)
    compound = [c for c in out if c.get("derived_from")]
    assert len(compound) >= 2 and all(c["atomic"] for c in compound)
    simple = [c for c in out if not c.get("atomic")]
    assert simple and simple[0]["fact"] == "돌봄 노동은 자동화가 느리다"
    # source_ids preserved onto atomic parts
    assert all(c["source_ids"] == ["s1"] for c in compound)


def test_checkworthy_skips_opinion_keeps_factual():
    assert fc.checkworthy("2026년 실업률은 3.1%였다") is True
    assert fc.checkworthy("개인적으로 이건 별로인 것 같다") is False


def test_enrich_downgrades_lone_source_verified():
    facts = [{"fact": "AI 일자리 영향은 크다", "status": "VERIFIED", "confidence": 0.85, "source_ids": ["s1"]}]
    sources = [{"id": "s1", "title": "AI 일자리 리포트", "snippet": "AI 일자리 영향 분석"}]
    out = fc.enrich_facts(facts, sources)
    assert out[0]["status"] == "PARTIALLY_VERIFIED"          # only 1 agreeing source
    assert out[0]["agreement_count"] == 1
    # two agreeing sources -> stays VERIFIED
    sources2 = sources + [{"id": "s2", "title": "다른 AI 일자리 글", "snippet": "AI 일자리 영향 크다"}]
    out2 = fc.enrich_facts(facts, sources2)
    assert out2[0]["status"] == "VERIFIED" and out2[0]["agreement_count"] >= 2


def test_enrich_caps_confidence_without_sources():
    facts = [{"fact": "출처 없는 주장", "status": "UNVERIFIED", "confidence": 0.9, "source_ids": []}]
    out = fc.enrich_facts(facts, [])
    assert out[0]["confidence"] <= 0.3


# ---- Hook agent: diversity + exaggeration guard ---------------------- #

def test_hook_exaggeration_flags():
    flags = hk.exaggeration_flags("모두가 이 직업을 잃는다, 100% 확실합니다", usable_fact_texts=[])
    assert any("absolute_claim" in f for f in flags)
    flags2 = hk.exaggeration_flags("3년간 20% 감소했다", usable_fact_texts=["수요가 20% 감소했다"])
    assert not any("unbacked_number" in f for f in flags2)     # 20 is backed
    flags3 = hk.exaggeration_flags("무려 999만 개가 사라진다", usable_fact_texts=["수요가 20% 감소했다"])
    assert any("unbacked_number" in f for f in flags3)


def test_hook_refine_keeps_min_and_penalises_exaggeration():
    raw = [
        {"text": "AI로 사라질 직업, 생각보다 가깝습니다", "style": "호기심", "score": 0.80},
        {"text": "모두가 말하지만 아무도 모르는 사실", "style": "정보격차", "score": 0.82},
        {"text": "AI로 사라질 직업, 생각보다 가깝습니다!", "style": "호기심", "score": 0.79},
    ]
    scored, meta = hk.refine(raw, platform="youtube_shorts", recent_hook_texts=[],
                             usable_fact_texts=[])
    assert len(scored) >= 3
    # the absolute-claim hook is penalised below the clean one
    by_text = {h["text"]: h["adjusted_score"] for h in scored}
    assert by_text["AI로 사라질 직업, 생각보다 가깝습니다"] > by_text["모두가 말하지만 아무도 모르는 사실"]
    assert meta["any_exaggeration"] is True


def test_hook_recent_similarity_penalty():
    raw = [{"text": "AI가 바꾸는 일자리의 미래", "style": "긴장", "score": 0.8}]
    scored, _ = hk.refine(raw, platform=None,
                          recent_hook_texts=["AI가 바꾸는 일자리의 미래"], usable_fact_texts=[])
    assert scored[0]["recent_penalty"] > 0
