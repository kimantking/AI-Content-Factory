from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FactStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONTRADICTED = "CONTRADICTED"


USABLE_FACT_STATUSES = {FactStatus.VERIFIED, FactStatus.PARTIALLY_VERIFIED}


class SourceItem(BaseModel):
    id: str
    url: str
    title: str
    snippet: str = ""
    published_at: str | None = None


class Fact(BaseModel):
    fact: str
    status: FactStatus
    confidence: float = 0.0
    source_ids: list[str] = Field(default_factory=list)
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.status in USABLE_FACT_STATUSES


class KnowledgePack(BaseModel):
    """Single Source of Truth for all downstream content."""

    topic: str
    audience: str = ""
    verified_facts: list[Fact] = Field(default_factory=list)
    statistics: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    sources: list[SourceItem] = Field(default_factory=list)
    counter_arguments: list[str] = Field(default_factory=list)
    interesting_points: list[str] = Field(default_factory=list)
    visual_opportunities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)

    def usable_facts(self) -> list[Fact]:
        return [f for f in self.verified_facts if f.usable]


class StrategyModel(BaseModel):
    angle: str
    key_message: str
    tone: str = ""
    target_emotion: str = ""
    talking_points: list[str] = Field(default_factory=list)


class HookModel(BaseModel):
    text: str
    style: str = ""
    score: float = 0.0


class ScriptModel(BaseModel):
    platform: str = "MASTER"
    body: str
    word_count: int = 0


class ScriptQAReport(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    used_unverified_fact: bool = False
    word_count: int = 0
