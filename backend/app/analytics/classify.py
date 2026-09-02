from __future__ import annotations

import re

HOOK_TYPES = ["QUESTION", "WARNING", "CURIOSITY_GAP", "STATISTIC", "LIST", "STORY",
              "CONTRARIAN", "PROBLEM", "PROMISE", "NEWS", "COMPARISON", "OTHER"]

CTA_TYPES = ["FOLLOW", "COMMENT", "SHARE", "SAVE", "LINK", "PRODUCT",
             "NEXT_EPISODE", "QUESTION", "NONE"]

_NUM = re.compile(r"\d")


def classify_hook(text: str) -> str:
    t = (text or "").strip().lower()
    if not t:
        return "OTHER"
    if t.endswith("?") or "까요" in t or "무엇" in t or "어떻게" in t:
        return "QUESTION"
    if any(k in t for k in ("사라질", "위험", "조심", "경고", "놓치면", "이것만은", "안 하면")):
        return "WARNING"
    if any(k in t for k in ("아무도", "모르는", "숨겨", "비밀", "말하지 않")):
        return "CURIOSITY_GAP"
    if _NUM.search(t) and any(k in t for k in ("%", "배", "년", "명", "만", "억")):
        return "STATISTIC"
    if any(k in t for k in ("가지", "가지 방법", "리스트", "top", "3가지", "5가지")):
        return "LIST"
    if any(k in t for k in ("제가", "그날", "어느 날", "예전에", "처음")):
        return "STORY"
    if any(k in t for k in ("사실은", "반대로", "틀렸", "착각", "오해")):
        return "CONTRARIAN"
    if any(k in t for k in ("문제는", "고민", "힘들", "안 되")):
        return "PROBLEM"
    if any(k in t for k in ("하면", "된다", "가능", "방법", "해결")):
        return "PROMISE"
    if any(k in t for k in ("발표", "출시", "속보", "이번", "최신", "오늘")):
        return "NEWS"
    if any(k in t for k in ("vs", "대", "비교", "차이")):
        return "COMPARISON"
    return "OTHER"


_CTA_MAP = {
    "question": "QUESTION", "comment": "COMMENT", "save": "SAVE", "share": "SHARE",
    "follow": "FOLLOW", "next_episode": "NEXT_EPISODE", "comparison": "COMMENT",
    "link": "LINK", "product": "PRODUCT", "none": "NONE",
}


def classify_cta(cta_type_hint: str | None, cta_text: str | None) -> str:
    if cta_type_hint and cta_type_hint.lower() in _CTA_MAP:
        return _CTA_MAP[cta_type_hint.lower()]
    t = (cta_text or "").lower()
    if not t:
        return "NONE"
    if "?" in t or "생각" in t:
        return "QUESTION"
    if "저장" in t:
        return "SAVE"
    if "공유" in t:
        return "SHARE"
    if "팔로우" in t or "구독" in t:
        return "FOLLOW"
    if "다음 편" in t or "다음편" in t:
        return "NEXT_EPISODE"
    if "댓글" in t:
        return "COMMENT"
    if "http" in t or "링크" in t:
        return "LINK"
    return "NONE"
