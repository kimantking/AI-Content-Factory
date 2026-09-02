from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.media_nodes import (
    edit_decision_node,
    gen_images_node,
    gen_voice_node,
    load_inputs_node,
    media_qa_node,
    persist_media_node,
    platform_adapt_node,
    platform_images_node,
    render_node,
    scene_plan_node,
    thumbnail_node,
    timing_subtitle_node,
    visual_direct_node,
)
from app.agents.media_state import MediaState


def build_media_graph(checkpointer=None):
    g = StateGraph(MediaState)

    g.add_node("load_inputs", load_inputs_node)
    g.add_node("platform_adapt", platform_adapt_node)
    g.add_node("scene_plan", scene_plan_node)
    g.add_node("visual_direct", visual_direct_node)
    g.add_node("gen_images", gen_images_node)
    g.add_node("gen_voice", gen_voice_node)
    g.add_node("timing_subtitle", timing_subtitle_node)
    g.add_node("edit_decision", edit_decision_node)
    g.add_node("render", render_node)
    g.add_node("thumbnail", thumbnail_node)
    g.add_node("platform_images", platform_images_node)
    g.add_node("run_media_qa", media_qa_node)
    g.add_node("persist_media", persist_media_node)

    order = [
        "load_inputs", "platform_adapt", "scene_plan", "visual_direct",
        "gen_images", "gen_voice", "timing_subtitle", "edit_decision",
        "render", "thumbnail", "platform_images", "run_media_qa", "persist_media",
    ]
    g.add_edge(START, order[0])
    for a, b in zip(order, order[1:]):
        g.add_edge(a, b)
    g.add_edge(order[-1], END)
    return g.compile(checkpointer=checkpointer)
