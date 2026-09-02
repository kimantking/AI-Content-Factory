from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.opensource import load_registry
from app.providers.registry import active_mode

router = APIRouter(prefix="/api", tags=["meta"])

PLATFORMS = [
    "YouTube", "YouTube Shorts", "TikTok", "Instagram", "Facebook",
    "Threads", "X", "Pinterest", "LinkedIn", "Naver Blog", "Naver Clip",
]
GOALS = ["Views", "Followers", "Revenue", "Profit", "Brand", "Balanced"]


@router.get("/config")
def config():
    s = get_settings()
    readiness = {
        "llm": not s.llm_is_mock,
        "search": not s.search_is_mock,
        "image": not s.media_provider_is_mock("image"),
        "video": not s.media_provider_is_mock("video"),
        "tts": not s.media_provider_is_mock("tts"),
        "publishing": not s.dry_run and s.platform_client == "http",
    }
    return {
        "mode": active_mode(),
        "mock_mode": s.mock_mode,
        "real_mode_ready": all(readiness[k] for k in ("llm", "search", "image", "video")),
        "readiness": readiness,
        "platforms": PLATFORMS,
        "goals": GOALS,
        "budget": {
            "campaign": s.campaign_budget_usd,
            "daily": s.daily_budget_usd,
            "monthly": s.monthly_budget_usd,
        },
        "natural_content": {
            "enabled": s.natural_writing_enabled,
            "max_ai_slop_score": s.max_ai_slop_score,
            "default_brand": s.default_brand,
        },
        "phase": "1-A",
    }


@router.get("/open-source-components")
def open_source_components():
    return [c.__dict__ for c in load_registry()]


# NOTE: `GET /api/providers` is served by app.api.routes_providers (the AI 연결
# credential + probe router) — a richer superset of the old status-only view.
# Kept here as an alias path so nothing that called it breaks.
@router.get("/providers/status")
def providers_status(probe: bool = True):
    """Provider connection status only (no secret values). `probe=false` skips
    network checks. See `GET /api/providers` for the full credential view."""
    from app.providers.status import provider_status

    return provider_status(probe=probe)
