from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.media import VISUAL_FALLBACK, VisualType


def _v(x) -> str:
    return x.value if isinstance(x, VisualType) else str(x)

_NUM = re.compile(r"\d[\d,.%]*")
_COMPARE = ("비교", "대비", "증가", "감소", "배", "%", "퍼센트", "수치", "통계", "비율")
_REAL_SCENE = ("현장", "실제", "거리", "사무실", "공장", "매장", "도시", "출근", "인터뷰", "장면")
_MOTION_HEAVY = ("빠르게", "역동", "움직", "변화가", "속도", "흐름", "밀려", "휩쓸")
_EMPHASIS = ("!", "기억하세요", "핵심", "단 하나", "지금", "결국")

_MOTIONS = ["SLOW_ZOOM_IN", "PAN_RIGHT", "SLOW_ZOOM_OUT", "PAN_LEFT", "KEN_BURNS", "PAN_UP"]


@dataclass
class VisualChoice:
    visual_type: str
    camera_motion: str
    reason: str
    downgraded_from: str | None = None


def _first_choice(narr: str, has_sources: bool, order: int) -> tuple[str, str]:
    t = narr.strip()
    words = t.split()
    if _NUM.search(t) and any(k in t for k in _COMPARE):
        return (VisualType.CHART if has_sources else VisualType.TEXT_CARD, "numbers+comparison")
    if len(words) <= 6 and any(k in t for k in _EMPHASIS):
        return VisualType.TEXT_CARD, "short emphasis line"
    if any(k in t for k in _REAL_SCENE):
        return VisualType.STOCK_VIDEO, "depicts a real scene"
    if sum(k in t for k in _MOTION_HEAVY) >= 1:
        return VisualType.AI_VIDEO, "motion-heavy description"
    return VisualType.AI_IMAGE, "general explanation"


def plan_visuals(
    scenes: list[dict],
    *,
    max_ai_video_ratio: float,
    video_provider_available: bool,
    stock_provider_available: bool,
    remaining_budget_usd: float,
    ai_video_unit_cost: float = 0.6,
    ai_image_unit_cost: float = 0.0,
) -> list[VisualChoice]:
    n = len(scenes)
    ai_video_cap = int(n * max_ai_video_ratio) if video_provider_available else 0
    ai_video_used = 0
    out: list[VisualChoice] = []
    for i, s in enumerate(scenes):
        motion = _MOTIONS[i % len(_MOTIONS)]
        vt, reason = _first_choice(
            s.get("narration", ""), bool(s.get("source_ids")), i
        )
        downgraded_from = None

        if vt == VisualType.AI_VIDEO:
            allow = (
                ai_video_used < ai_video_cap
                and remaining_budget_usd >= ai_video_unit_cost
                and video_provider_available
            )
            if allow:
                ai_video_used += 1
                remaining_budget_usd -= ai_video_unit_cost
            else:
                downgraded_from = vt
                vt = VisualType.AI_IMAGE
                reason = "AI_VIDEO unavailable/over-budget → image-motion fallback"

        if vt == VisualType.STOCK_VIDEO and not stock_provider_available:
            downgraded_from = downgraded_from or VisualType.STOCK_VIDEO
            vt = VISUAL_FALLBACK[VisualType.STOCK_VIDEO][0]
            reason = "no stock provider → fallback"

        if vt == VisualType.CHART and not s.get("source_ids"):
            downgraded_from = downgraded_from or VisualType.CHART
            vt = VisualType.TEXT_CARD
            reason = "chart needs verified source_ids → text card"

        out.append(VisualChoice(visual_type=_v(vt), camera_motion=motion,
                                reason=reason, downgraded_from=_v(downgraded_from) if downgraded_from else None))
    return out
