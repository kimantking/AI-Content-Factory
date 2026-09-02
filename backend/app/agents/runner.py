from __future__ import annotations

import contextlib
from typing import Any

from app.agents.graph import build_graph
from app.agents.state import initial_state
from app.config import get_settings


@contextlib.contextmanager
def _checkpointer():
    """Yield a LangGraph checkpointer. Postgres by default (durable, resumable);
    in-memory only when explicitly configured (tests that don't need resume)."""
    s = get_settings()
    kind = getattr(s, "checkpointer_kind", "postgres")
    if kind == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        yield InMemorySaver()
        return

    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(s.sync_database_url) as cp:
        cp.setup()
        yield cp


def _config(campaign_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": campaign_id}, "recursion_limit": 50}


def run_pipeline(
    campaign_id: str,
    topic: str,
    audience_goal: str = "BALANCED",
    platforms: list[str] | None = None,
    *,
    resume: bool = False,
) -> dict:
    """Run (or resume) the Phase 1-A LangGraph pipeline for one campaign.

    campaign_id doubles as the LangGraph thread_id, so a restarted process
    resumes from the last completed node.
    """
    with _checkpointer() as cp:
        graph = build_graph(checkpointer=cp)
        cfg = _config(campaign_id)
        if resume:
            return graph.invoke(None, cfg)
        state = initial_state(campaign_id, topic, audience_goal, platforms or [])
        return graph.invoke(state, cfg)


def get_state(campaign_id: str) -> dict:
    with _checkpointer() as cp:
        graph = build_graph(checkpointer=cp)
        snap = graph.get_state(_config(campaign_id))
        return {"values": snap.values, "next": list(snap.next)}
