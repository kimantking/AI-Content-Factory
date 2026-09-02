from __future__ import annotations

import hashlib

# Design Amendment §33 — CTA variation. Avoid repeating the same closer.

CTA_LIBRARY: dict[str, list[str]] = {
    "question": [
        "당신 일에서는 이미 바뀐 게 있나요? 댓글로 알려주세요.",
        "가장 먼저 영향을 받을 직군이 뭐라고 보세요?",
    ],
    "save": [
        "나중에 다시 볼 수 있게 저장해두세요.",
        "체크리스트로 쓸 수 있으니 저장 추천합니다.",
    ],
    "share": [
        "비슷한 고민 하는 사람한테 공유해도 좋아요.",
        "이 얘기 필요할 것 같은 사람 한 명 떠오르면 보내주세요.",
    ],
    "follow": [
        "다음 편도 이어서 다룹니다. 팔로우해두세요.",
        "이 주제 계속 파고들 예정이에요. 팔로우로 놓치지 마세요.",
    ],
    "next_episode": [
        "다음 편에서는 구체적인 대응 방법을 정리합니다.",
        "다음 편 주제는 '지금 당장 배워둘 것'입니다.",
    ],
    "comparison": [
        "2년 전과 지금을 비교해보면 차이가 분명합니다. 다음 편에서 정리할게요.",
    ],
    "none": [""],
}

_ORDER = ["question", "save", "share", "follow", "next_episode", "comparison"]


def pick_cta(seed: str, recent_types: list[str] | None = None) -> tuple[str, str]:
    """Deterministic-but-rotating CTA choice. Skips the last few used types."""
    recent = recent_types or []
    blocked = set(recent[-3:])
    candidates = [t for t in _ORDER if t not in blocked] or _ORDER
    idx = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % len(candidates)
    ctype = candidates[idx]
    variants = CTA_LIBRARY.get(ctype) or [""]
    vidx = int(hashlib.sha256((seed + ctype).encode("utf-8")).hexdigest()[8:16], 16) % len(variants)
    return ctype, variants[vidx]
