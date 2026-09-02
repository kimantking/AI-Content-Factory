from __future__ import annotations

from pydantic import BaseModel, Field

GOALS = {"VIEWS", "FOLLOWERS", "REVENUE", "PROFIT", "BRAND", "BALANCED"}


class CreateCampaignRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=500)
    audience_goal: str = "BALANCED"
    platforms: list[str] = Field(default_factory=list)

    def normalized_goal(self) -> str:
        g = (self.audience_goal or "BALANCED").upper()
        return g if g in GOALS else "BALANCED"


class CampaignSummary(BaseModel):
    id: str
    topic: str
    status: str
    current_step: str | None
    audience_goal: str
    fact_score: float | None
    created_at: str


class StepStatus(BaseModel):
    name: str
    status: str


class CampaignDetail(CampaignSummary):
    platforms: list[str]
    knowledge_pack: dict | None
    error_message: str | None
    steps: list[StepStatus]
    sources: list[dict]
    verified_facts: list[dict]
    strategy: dict | None
    hooks: list[dict]
    script: dict | None
    agent_runs: list[dict]
    cost_usd: float
    budget: dict
