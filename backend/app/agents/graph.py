from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    create_campaign_node,
    fact_check_node,
    fact_score_router,
    hook_node,
    persist_node,
    research_fix_node,
    research_node,
    script_node,
    script_qa_node,
    strategy_node,
)
from app.agents.state import PipelineState


def build_graph(checkpointer=None):
    g = StateGraph(PipelineState)

    g.add_node("create_campaign", create_campaign_node)
    g.add_node("research", research_node)
    g.add_node("fact_check", fact_check_node)
    g.add_node("research_fix", research_fix_node)
    g.add_node("strategize", strategy_node)
    g.add_node("hook", hook_node)
    g.add_node("write_script", script_node)
    g.add_node("qa_script", script_qa_node)
    g.add_node("persist", persist_node)

    g.add_edge(START, "create_campaign")
    g.add_edge("create_campaign", "research")
    g.add_edge("research", "fact_check")
    g.add_conditional_edges(
        "fact_check",
        fact_score_router,
        {"research_fix": "research_fix", "strategize": "strategize"},
    )
    g.add_edge("research_fix", "fact_check")
    g.add_edge("strategize", "hook")
    g.add_edge("hook", "write_script")
    g.add_edge("write_script", "qa_script")
    g.add_edge("qa_script", "persist")
    g.add_edge("persist", END)

    return g.compile(checkpointer=checkpointer)
