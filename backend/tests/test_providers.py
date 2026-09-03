from __future__ import annotations

import json

from app.providers.mock_llm import MockLLMProvider
from app.providers.mock_search import MockSearchProvider
from app.providers.ollama_llm import OllamaLLMProvider
from app.providers.registry import get_llm_provider, get_search_provider


def test_mock_search_is_deterministic():
    a = MockSearchProvider().search("한국 취업시장", max_results=6)
    b = MockSearchProvider().search("한국 취업시장", max_results=6)
    assert len(a) == 6
    assert [r.url for r in a] == [r.url for r in b]
    assert a[0].url != MockSearchProvider().search("다른 주제")[0].url


def test_mock_llm_task_outputs_are_json_and_stable():
    llm = MockLLMProvider()
    ctx = {"topic": "AI 직업", "sources": [{"id": "s1", "title": "t", "snippet": "x"}]}
    r1 = llm.complete(system="s", user="u", task="research", context=ctx)
    r2 = llm.complete(system="s", user="u", task="research", context=ctx)
    assert r1.text == r2.text
    assert r1.provider == "mock" and r1.output_tokens > 0
    import json

    data = json.loads(r1.text)
    assert data["candidate_facts"] and all("source_ids" in f for f in data["candidate_facts"])


def test_registry_selects_mock_in_mock_mode(_base_settings):
    assert isinstance(get_llm_provider(), MockLLMProvider)
    assert isinstance(get_search_provider(), MockSearchProvider)


def test_registry_would_select_real_when_configured(_base_settings):
    s = _base_settings
    s.mock_mode = False
    s.llm_provider = "anthropic"
    s.anthropic_api_key = "sk-test"
    # constructing the real adapter imports anthropic; just assert selection logic
    assert not s.llm_is_mock


def test_registry_selects_ollama_as_real_primary(_base_settings):
    s = _base_settings
    s.mock_mode = False
    s.llm_provider = "ollama"
    s.ollama_enabled = True
    provider = get_llm_provider()
    assert not s.llm_is_mock
    assert isinstance(provider, OllamaLLMProvider)
    assert provider.model == s.ollama_default_model


def test_registry_selects_agent_reach_as_real_search(_base_settings):
    from app.providers.agent_reach_search import AgentReachSearchProvider

    s = _base_settings
    s.mock_mode = False
    s.agent_reach_enabled = True
    s.search_provider = "tavily"
    s.tavily_api_key = None
    provider = get_search_provider()
    assert not s.search_is_mock
    assert isinstance(provider, AgentReachSearchProvider)


def test_ollama_plain_text_chat_is_wrapped_as_valid_json(monkeypatch):
    from app.providers.ollama_llm import OllamaLLMProvider

    provider = OllamaLLMProvider(model="gemma3:4b")
    captured = {}

    def fake_request(_path, payload):
        captured.update(payload)
        return {"message": {"content": "긴 대본도 그대로 반환합니다."}}

    monkeypatch.setattr(provider, "_request", fake_request)
    response = provider.complete(system="대본 전문가", user="대본 작성", task="agent_chat",
                                 context={"plain_text": True, "max_tokens": 1400})
    assert json.loads(response.text) == {"reply": "긴 대본도 그대로 반환합니다."}
    assert "format" not in captured
