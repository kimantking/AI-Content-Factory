from __future__ import annotations

import re
from pathlib import Path

from app.media.draw import gradient_bg, wrap_by_width
from app.media.fonts import load_font
from app.schemas.media import ThumbnailConcept

# YouTube thumbnail = AI/mock background + code-composited text overlay (kept
# separate so the model never renders long Korean text into an image).

_STOP = {"그리고", "하지만", "그러나", "the", "a", "of", "to", "및", "수", "것"}


def propose_concepts(topic: str, key_message: str, hook: str) -> list[ThumbnailConcept]:
    kws = [w for w in re.findall(r"[\w가-힣]+", f"{hook} {key_message} {topic}") if w not in _STOP]
    lead = " ".join(kws[:3]) or topic[:16]
    return [
        ThumbnailConcept(headline=lead, visual_subject=topic[:40], emotion="긴장",
                         composition="left-text / right-subject", background="어두운 그라디언트",
                         contrast_strategy="밝은 텍스트 + 어두운 배경"),
        ThumbnailConcept(headline=(hook[:22] or lead), visual_subject=topic[:40], emotion="호기심",
                         composition="center headline", background="포인트 컬러 블록",
                         contrast_strategy="보색 대비"),
        ThumbnailConcept(headline=f"{lead}?", visual_subject=topic[:40], emotion="의문",
                         composition="bottom-third text", background="사진풍 배경(mock)",
                         contrast_strategy="큰 물음표 아이콘"),
    ]


def _score(c: ThumbnailConcept) -> dict[str, float]:
    words = len(c.headline.split())
    clarity = max(0.3, 1.0 - abs(words - 3) * 0.15)
    curiosity = 0.8 if c.headline.strip().endswith("?") else 0.6
    readability = max(0.3, 1.0 - max(0, len(c.headline) - 18) * 0.04)
    relevance = 0.7
    brand_fit = 0.7
    return {"clarity": round(clarity, 2), "curiosity": round(curiosity, 2),
            "relevance": relevance, "readability": round(readability, 2),
            "brand_fit": brand_fit}


def render_concept(c: ThumbnailConcept, out_path: str, *, width: int = 1280, height: int = 720,
                   mock: bool = True) -> ThumbnailConcept:
    from PIL import ImageDraw

    img = gradient_bg(width, height, c.headline + c.visual_subject).convert("RGB")
    d = ImageDraw.Draw(img)
    font = load_font(max(44, width // 14), bold=True)
    max_w = int(width * 0.6)
    lines = wrap_by_width(d, c.headline, font, max_w)[:3]
    lh = int(font.size * 1.2)
    y = (height - lh * len(lines)) // 2
    for ln in lines:
        d.text((int(width * 0.06), y), ln, font=font, fill=(250, 250, 250),
               stroke_width=4, stroke_fill=(0, 0, 0))
        y += lh
    if mock:
        wm = load_font(max(14, width // 48), bold=True)
        d.rectangle([10, 10, 150, 40], fill=(0, 0, 0))
        d.text((16, 14), "MOCK THUMBNAIL", font=wm, fill=(255, 90, 90))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    c.scores = _score(c)
    return c
