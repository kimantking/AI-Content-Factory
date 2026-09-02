from __future__ import annotations

from app.config import get_settings
from app.providers.base import LLMProvider, SearchProvider
from app.providers.mock_llm import MockLLMProvider
from app.providers.mock_search import MockSearchProvider


def get_llm_provider() -> LLMProvider:
    s = get_settings()
    if s.llm_is_mock:
        return MockLLMProvider()
    from app.providers.anthropic_llm import AnthropicLLMProvider

    return AnthropicLLMProvider(api_key=s.anthropic_api_key or "", model=s.anthropic_model,
                                workspace_id=getattr(s, "anthropic_workspace_id", ""))


def get_search_provider() -> SearchProvider:
    s = get_settings()
    if s.search_is_mock:
        return MockSearchProvider()
    from app.providers.tavily_search import TavilySearchProvider

    return TavilySearchProvider(api_key=s.tavily_api_key or "")


def active_mode() -> str:
    s = get_settings()
    llm = "mock" if s.llm_is_mock else s.llm_provider
    search = "mock" if s.search_is_mock else s.search_provider
    return f"llm={llm} search={search}"
