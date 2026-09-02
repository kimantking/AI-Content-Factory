from __future__ import annotations

import os
from functools import lru_cache

# Prefer a Korean-capable TTF. Falls back gracefully; text still lays out even if
# glyphs are missing.
_CANDIDATES_REGULAR = [
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\NotoSansKR-VF.ttf",
    r"C:\Windows\Fonts\NGULIM.TTF",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]
_CANDIDATES_BOLD = [
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\NotoSansKR-VF.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


@lru_cache
def regular_font_path() -> str | None:
    return _first_existing(_CANDIDATES_REGULAR)


@lru_cache
def bold_font_path() -> str | None:
    return _first_existing(_CANDIDATES_BOLD) or regular_font_path()


@lru_cache(maxsize=64)
def load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    path = bold_font_path() if bold else regular_font_path()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()
