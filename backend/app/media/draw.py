from __future__ import annotations

import hashlib
import textwrap

from app.media.fonts import load_font


def _hue_from(seed: str) -> tuple[int, int, int]:
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    # muted, non-garish palette
    base = (40 + h[0] % 60, 40 + h[1] % 60, 60 + h[2] % 80)
    return base


def gradient_bg(w: int, h: int, seed: str):
    from PIL import Image

    c1 = _hue_from(seed)
    c2 = _hue_from(seed[::-1])
    img = Image.new("RGB", (w, h), c1)
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        row = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = row
    return img


def wrap_by_width(draw, text: str, font, max_width: int) -> list[str]:
    """Greedy wrap that also works for spaceless Korean by falling back to
    character-level breaks."""
    words = text.split()
    lines: list[str] = []
    if words and max(draw.textlength(w, font=font) for w in words) <= max_width:
        cur = ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if draw.textlength(trial, font=font) <= max_width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines
    # char-level
    cur = ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_width:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def placeholder_card(
    w: int, h: int, *, title: str, subtitle: str = "", seed: str = "acf",
    watermark: str = "MOCK ASSET",
):
    """A clearly-labelled MOCK image (Design/Amendment rule: never disguise a mock
    as a real generation)."""
    from PIL import Image, ImageDraw

    img = gradient_bg(w, h, seed).convert("RGB")
    d = ImageDraw.Draw(img)

    title_font = load_font(max(28, w // 18), bold=True)
    sub_font = load_font(max(18, w // 34))
    wm_font = load_font(max(14, w // 48), bold=True)

    margin = int(w * 0.08)
    lines = wrap_by_width(d, title, title_font, w - 2 * margin)[:4]
    line_h = int(title_font.size * 1.3)
    total_h = line_h * len(lines) + (int(sub_font.size * 1.4) if subtitle else 0)
    y = (h - total_h) // 2
    for ln in lines:
        tw = d.textlength(ln, font=title_font)
        d.text(((w - tw) / 2, y), ln, font=title_font, fill=(245, 245, 245))
        y += line_h
    if subtitle:
        for sub_ln in textwrap.wrap(subtitle, width=40)[:2]:
            tw = d.textlength(sub_ln, font=sub_font)
            d.text(((w - tw) / 2, y), sub_ln, font=sub_font, fill=(210, 210, 210))
            y += int(sub_font.size * 1.4)

    # corner watermark (only for genuine MOCK assets — omit for code-rendered cards)
    if watermark:
        pad = int(w * 0.02)
        wm = f"{watermark}"
        tw = d.textlength(wm, font=wm_font)
        d.rectangle([pad, pad, pad * 2 + tw, pad + wm_font.size + pad], fill=(0, 0, 0))
        d.text((pad * 1.5, pad * 1.2), wm, font=wm_font, fill=(255, 90, 90))
    return img
