"""Model pricing table with explicit KNOWN / ESTIMATED / UNKNOWN state.

No fabricated numbers. A cloud model whose current price we have not verified is
`UNKNOWN` and the cost estimate says so. Local (Ollama) API cost is a real 0 —
but compute is not "free", so the UI phrases it as "LOCAL PROCESSING · API ₩0".
"""
from __future__ import annotations

# model_id -> (input_usd_per_1k, output_usd_per_1k, state)
# state: KNOWN (verified) | ESTIMATED (public list price, approximate) | UNKNOWN
_PRICES: dict[str, tuple[float, float, str]] = {
    # local — real zero API cost
    "gemma3:4b":          (0.0, 0.0, "KNOWN"),
    "ollama:*":           (0.0, 0.0, "KNOWN"),
    "mock":               (0.0, 0.0, "KNOWN"),   # MOCK MODE stand-in — free, labelled
    # cloud — public list prices as of the knowledge cutoff; treat as ESTIMATED,
    # operators verify before enabling a paid provider (DECISIONS D10).
    "claude-haiku-4-5-20251001": (0.001, 0.005, "ESTIMATED"),
    "claude-sonnet-5":    (0.003, 0.015, "ESTIMATED"),
    "claude-opus-5":      (0.015, 0.075, "ESTIMATED"),
}

USD_KRW = 1350  # display-only rough conversion; flagged approximate in the UI


def price_for(model_id: str) -> tuple[float, float, str]:
    if model_id in _PRICES:
        return _PRICES[model_id]
    if model_id.startswith("ollama:") or model_id.startswith("gemma") or "@" in model_id:
        return (0.0, 0.0, "KNOWN")
    return (0.0, 0.0, "UNKNOWN")


def cost_of(model_id: str, *, input_tokens: int, output_tokens: int) -> dict:
    inp, out, state = price_for(model_id)
    if state == "UNKNOWN":
        return {"usd": None, "state": "UNKNOWN", "model": model_id}
    usd = round(inp * input_tokens / 1000 + out * output_tokens / 1000, 6)
    return {"usd": usd, "state": state, "model": model_id,
            "local": state == "KNOWN" and inp == 0.0 and out == 0.0}
