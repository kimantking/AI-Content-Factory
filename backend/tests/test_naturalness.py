from __future__ import annotations

from app.naturalness import load_voice_profile, natural_writing_pass, score_ai_slop
from app.naturalness.cta import pick_cta

_SLOP_DRAFT = (
    "안녕하세요 여러분. 오늘은 인공지능에 대해 알아보겠습니다. "
    "인공지능은 중요합니다. 그리고 인공지능은 빠르게 발전합니다. "
    "그리고 많은 직업이 바뀝니다. 그리고 우리는 준비해야 합니다. "
    "결론적으로 인공지능은 중요합니다. 여러분은 어떻게 생각하시나요?"
)


def test_slop_scorer_flags_machine_like_text():
    rep = score_ai_slop(_SLOP_DRAFT)
    assert rep.score > 20
    assert any("접속어" in t or "관용구" in t or "도입부" in t for t in rep.tells)


def test_slop_scorer_rewards_varied_text():
    natural = (
        "AI가 일자리를 바꾼다. 속도가 문제다.\n\n"
        "번역과 단순 데이터 입력은 이미 자동화가 빠르게 진행됐고, 통계도 그 방향을 가리킨다. "
        "반대로 돌봄이나 현장 수리처럼 몸을 쓰는 일은 훨씬 느리게 움직인다.\n\n"
        "그래서 지금 할 일은 하나다. 내 업무 중 반복적인 조각을 찾아 하나만 자동화해 보는 것."
    )
    assert score_ai_slop(natural).score <= 20


def test_natural_writing_pass_reduces_slop_and_preserves_facts():
    facts = ["번역 수요가 3년간 20% 줄었다"]
    draft = (
        "안녕하세요 여러분. 오늘은 이 주제를 봅니다. 그리고 번역 수요가 3년간 20% 줄었다. "
        "그리고 이것은 중요합니다. 그리고 우리는 준비해야 합니다. 결론적으로 중요합니다."
    )
    res = natural_writing_pass(draft, voice=load_voice_profile("default"),
                               usable_facts=facts, unusable_facts=[])
    assert res.fact_preserved
    assert "20%" in res.text
    assert res.slop_after.score <= res.slop_before.score
    assert "안녕하세요 여러분" not in res.text


def test_natural_writing_pass_reverts_when_fact_lost(monkeypatch):
    draft = "핵심 사실 A는 참이다. 두 번째 문장. 세 번째 문장이다."

    class BadLLM:
        def complete(self, **kw):
            from app.providers.base import LLMResponse

            return LLMResponse(text='{"body": "완전히 다른 내용."}', input_tokens=1,
                               output_tokens=1, provider="mock", model="m")

    res = natural_writing_pass(draft, voice=load_voice_profile("default"),
                               usable_facts=["핵심 사실 A는 참이다"], unusable_facts=[], llm=BadLLM())
    assert res.fact_preserved is False
    assert res.text == draft


def test_natural_writing_never_invents_numbers():
    draft = "매출이 늘었다. 그리고 비용도 늘었다. 그리고 이익은 유지됐다."
    res = natural_writing_pass(draft, voice=load_voice_profile("default"),
                               usable_facts=[], unusable_facts=[])
    import re

    assert not re.search(r"\d", res.text)


def test_cta_rotates_and_avoids_recent():
    ctype, text = pick_cta(seed="camp-1", recent_types=["question", "save", "share"])
    assert ctype not in {"question", "save", "share"}
    assert isinstance(text, str)
