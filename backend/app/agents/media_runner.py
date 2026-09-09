from __future__ import annotations

import contextlib
from typing import Any

from app.agents.media_graph import build_media_graph
from app.agents.media_state import initial_media_state
from app.config import get_settings


@contextlib.contextmanager
def _checkpointer():
    s = get_settings()
    if getattr(s, "checkpointer_kind", "postgres") == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        yield InMemorySaver()
        return
    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(s.sync_database_url) as cp:
        cp.setup()
        yield cp


def _config(campaign_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": f"media:{campaign_id}"}, "recursion_limit": 50}


def run_media_pipeline(campaign_id: str, platforms: list[str] | None = None,
                       *, resume: bool = False) -> dict:
    from app.db.base import session_scope
    from app.db.models import Campaign
    from app.providers.media.runtime import media_workspace

    with session_scope() as session:
        camp = session.get(Campaign, campaign_id)
        if camp is None:
            raise ValueError("campaign not found")
        workspace_id = camp.workspace_id
        video_mode = camp.video_mode
    with media_workspace(workspace_id), _checkpointer() as cp:
        if not get_settings().mock_mode:
            from app.providers.media.registry import get_image_provider, get_tts_provider, get_video_provider
            from app.media.ffmpeg import run_ffmpeg

            get_image_provider()
            if video_mode != "IMAGE_MOTION":
                get_video_provider()
            from app.providers.media.preflight import validate_media_setup

            validate_media_setup(workspace_id, video_mode)
            tts = get_tts_provider()
            tts.validate_configuration()
            run_ffmpeg(["-version"], timeout=15)
        graph = build_media_graph(checkpointer=cp)
        cfg = _config(campaign_id)
        if resume and graph.get_state(cfg).next:
            return graph.invoke(None, cfg)
        return graph.invoke(initial_media_state(campaign_id, platforms or []), cfg)


def get_media_state(campaign_id: str) -> dict:
    with _checkpointer() as cp:
        graph = build_media_graph(checkpointer=cp)
        snap = graph.get_state(_config(campaign_id))
        return {"values": snap.values, "next": list(snap.next)}
