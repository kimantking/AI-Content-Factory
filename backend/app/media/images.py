from __future__ import annotations

from pathlib import Path

from app.media.draw import gradient_bg, wrap_by_width
from app.media.fonts import load_font
from app.schemas.media import CarouselPage

# Code-composited platform images. AI/mock art is the background; all real text is
# overlaid here so glyphs are always correct.


def _text_image(w: int, h: int, *, headline: str, body: str = "", seed: str = "",
                tag: str = "MOCK IMAGE", footer: str = ""):
    from PIL import ImageDraw

    img = gradient_bg(w, h, seed or headline).convert("RGB")
    d = ImageDraw.Draw(img)
    hfont = load_font(max(34, w // 16), bold=True)
    bfont = load_font(max(20, w // 32))
    m = int(w * 0.09)
    y = int(h * 0.14)
    for ln in wrap_by_width(d, headline, hfont, w - 2 * m)[:4]:
        d.text((m, y), ln, font=hfont, fill=(248, 248, 248), stroke_width=3, stroke_fill=(0, 0, 0))
        y += int(hfont.size * 1.25)
    if body:
        y += int(h * 0.03)
        for ln in wrap_by_width(d, body, bfont, w - 2 * m)[:8]:
            d.text((m, y), ln, font=bfont, fill=(226, 226, 226))
            y += int(bfont.size * 1.4)
    if footer:
        d.text((m, h - int(h * 0.09)), footer, font=bfont, fill=(200, 200, 200))
    wm = load_font(max(13, w // 52), bold=True)
    d.rectangle([8, 8, 8 + int(d.textlength(tag, font=wm)) + 16, 8 + wm.size + 12], fill=(0, 0, 0))
    d.text((16, 12), tag, font=wm, fill=(255, 90, 90))
    return img


def render_single(path: str, *, w: int, h: int, headline: str, body: str = "", seed: str = "") -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    _text_image(w, h, headline=headline, body=body, seed=seed).save(path, "PNG")
    return path


def carousel_pages(topic: str, key_message: str, facts: list[str], cta: str) -> list[CarouselPage]:
    pages = [CarouselPage(page_number=1, headline=topic[:60], body=key_message[:120],
                          layout_type="cover")]
    for i, f in enumerate(facts[:4], start=2):
        pages.append(CarouselPage(page_number=i, headline=f"포인트 {i - 1}", body=f[:160],
                                  layout_type="key-point"))
    pages.append(CarouselPage(page_number=len(pages) + 1, headline="정리", body=key_message[:160],
                              layout_type="summary"))
    pages.append(CarouselPage(page_number=len(pages) + 1, headline="", body=cta[:120],
                              layout_type="cta"))
    return pages


def render_carousel(pages: list[CarouselPage], out_dir: str, *, w: int, h: int) -> list[str]:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = []
    for p in pages:
        path = str(Path(out_dir) / f"carousel_{p.page_number:02d}.png")
        _text_image(w, h, headline=p.headline or "•", body=p.body,
                    seed=f"{p.page_number}:{p.headline}",
                    footer=f"{p.page_number}/{len(pages)}").save(path, "PNG")
        out.append(path)
    return out
