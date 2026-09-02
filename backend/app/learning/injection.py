from __future__ import annotations

from app.config import get_settings
from app.learning.memory import retrieve_memories

# Memory is STRATEGIC GUIDANCE, never FACT. It is injected into the Strategy step,
# never allowed to override the Knowledge Pack.


def strategy_memory_context(session, *, topic: str, platforms: list[str],
                            objective: str | None = None, brand_id: str | None = None) -> dict:
    s = get_settings()
    if not s.memory_injection_enabled:
        return {"enabled": False, "items": [], "text": ""}
    objective = (objective or s.default_objective).upper()
    # retrieve for the first platform of interest (or all) — keep it small
    platform = platforms[0] if platforms else None
    mems = retrieve_memories(session, platform=platform, topic=topic, objective=objective,
                             brand_id=brand_id)
    items = [{
        "type": m.memory_type, "statement": m.statement,
        "recommendation": m.recommendation, "confidence": m.confidence,
        "sample_size": m.sample_size, "status": m.status,
        "evidence_ids": (m.evidence_ids or [])[:3],
    } for m in mems]
    lines = [
        "STRATEGIC GUIDANCE (past performance — correlation, not fact; do not override verified facts):",
    ]
    for it in items:
        lines.append(f"- ({it['status']}, n={it['sample_size']}, conf={it['confidence']}) {it['statement']}")
    return {"enabled": True, "objective": objective, "items": items,
            "text": "\n".join(lines) if items else ""}
