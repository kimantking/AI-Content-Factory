from __future__ import annotations

# USD per 1M tokens. Mock is free. Real prices are placeholders — update from the
# official pricing page before enabling a paid provider (see docs/DECISIONS.md).
_PRICE_PER_MTOK: dict[tuple[str, str], tuple[float, float]] = {
    ("mock", "mock-llm-v1"): (0.0, 0.0),
    ("mock", "mock"): (0.0, 0.0),                   # router MOCK MODE stand-in
    ("anthropic", "claude-sonnet-5"): (3.0, 15.0),  # PLACEHOLDER
}

_SEARCH_PRICE_PER_CALL: dict[str, float] = {
    "mock": 0.0,
    "agent_reach": 0.0,  # local/read-only upstream tools
    "tavily": 0.008,  # PLACEHOLDER
}


def llm_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = _PRICE_PER_MTOK.get((provider, model), (0.0, 0.0))
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def search_cost(provider: str, calls: int = 1) -> float:
    return _SEARCH_PRICE_PER_CALL.get(provider, 0.0) * calls


def log_cost(
    session,
    *,
    campaign_id: str | None,
    agent_name: str,
    kind: str,
    provider: str,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    amount_usd: float = 0.0,
) -> None:
    from app.db.models import CostLog

    session.add(
        CostLog(
            campaign_id=campaign_id,
            agent_name=agent_name,
            kind=kind,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            amount_usd=amount_usd,
        )
    )
    session.flush()
