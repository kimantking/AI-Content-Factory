from __future__ import annotations

from typing import Any, TypedDict


class MediaState(TypedDict, total=False):
    campaign_id: str
    requested_platforms: list[str]
    primary_platform: str            # the video platform we fully render this run

    kp: dict[str, Any]
    usable_fact_texts: list[str]
    fact_source_ids: dict[str, list[str]]
    master_hook: str
    master_script: str
    strategy: dict[str, Any]

    content_id: str
    platform_content: dict[str, Any]
    scenes: list[dict[str, Any]]     # serialised Scene rows (+ derived fields)
    creative_plan: dict[str, Any]    # Video Studio Upgrade — VideoCreativePlan.to_dict()
    quality_profile: str             # FAST | STANDARD | PREMIUM | CINEMATIC
    video_qa: dict[str, Any]

    word_timings: list[dict[str, Any]]
    subtitle_blocks: list[dict[str, Any]]
    subtitle_coverage: float

    render_path: str
    render_asset_id: str
    thumbnail_ids: list[str]
    platform_image_ids: list[str]

    media_qa: dict[str, Any]
    content_qa: dict[str, Any]
    compliance: dict[str, Any]

    status: str
    errors: list[dict[str, Any]]


def initial_media_state(campaign_id: str, platforms: list[str]) -> MediaState:
    return MediaState(
        campaign_id=campaign_id,
        requested_platforms=platforms,
        status="RUNNING",
        errors=[],
    )
