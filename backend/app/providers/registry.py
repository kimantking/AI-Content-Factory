from __future__ import annotations

from app.config import get_settings
from app.providers.base import LLMProvider, SearchProvider
from app.providers.mock_llm import MockLLMProvider
from app.providers.mock_search import MockSearchProvider
from app.providers.errors import ProviderError


def get_llm_provider() -> LLMProvider:
    s = get_settings()
    if s.mock_mode:
        return MockLLMProvider()
    if s.llm_provider == "ollama":
        if not s.ollama_enabled:
            raise ProviderError("OLLAMA_ENABLED=true가 필요합니다", "AUTH_ERROR")
        from app.providers.ollama_llm import OllamaLLMProvider

        return OllamaLLMProvider(base_url=s.ollama_base_url, model=s.ollama_default_model,
                                 timeout_seconds=s.local_model_timeout_seconds)
    if s.llm_provider != "anthropic" or not s.anthropic_api_key:
        raise ProviderError(
            f"실사용 LLM이 연결되지 않았습니다 (LLM_PROVIDER={s.llm_provider})",
            "AUTH_ERROR",
        )
    from app.providers.anthropic_llm import AnthropicLLMProvider

    return AnthropicLLMProvider(api_key=s.anthropic_api_key or "", model=s.anthropic_model,
                                workspace_id=getattr(s, "anthropic_workspace_id", ""))


def get_search_provider() -> SearchProvider:
    s = get_settings()
    if s.mock_mode:
        return MockSearchProvider()
    fallback = None
    if s.tavily_api_key and (s.search_provider == "tavily" or s.agent_reach_enabled):
        from app.providers.tavily_search import TavilySearchProvider

        fallback = TavilySearchProvider(api_key=s.tavily_api_key)
    if s.agent_reach_enabled:
        from app.providers.agent_reach_search import AgentReachSearchProvider

        return AgentReachSearchProvider(fallback=fallback)
    if fallback is not None:
        return fallback
    raise ProviderError(
        "실사용 검색이 연결되지 않았습니다. Agent Reach를 활성화하거나 Tavily 키를 설정하세요.",
        "AUTH_ERROR",
    )


def active_mode() -> str:
    s = get_settings()
    llm = "mock" if s.llm_is_mock else s.llm_provider
    search = get_search_provider().name
    return f"llm={llm} search={search}"
