from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class LLMResponse(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int
    provider: str
    model: str


class SearchResultItem(BaseModel):
    url: str
    title: str
    snippet: str = ""
    published_at: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, *, system: str, user: str, task: str, context: dict) -> LLMResponse: ...


@runtime_checkable
class SearchProvider(Protocol):
    name: str

    def search(self, query: str, *, max_results: int = 6) -> list[SearchResultItem]: ...
