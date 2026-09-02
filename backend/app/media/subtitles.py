from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.media.draw import wrap_by_width
from app.media.fonts import load_font
from app.schemas.media import SubtitleBlock, WordTiming

# Korean phrase-unit line breaking (Design Amendment §12): break AFTER particles /
# clause endings, never mid-phrase.
_BREAK_AFTER = (
    "은", "는", "이", "가", "을", "를", "에", "에서", "으로", "로", "와", "과",
    "도", "만", "까지", "부터", "고", "며", "지만", "는데", "면", "서", "요", "다",
)
_NUM_RE = re.compile(r"\d[\d,.%]*")


def phrase_units(text: str) -> list[str]:
    rough = re.split(r"(?<=[.!?…,])\s+", text.strip())
    units: list[str] = []
    for chunk in rough:
        chunk = chunk.strip()
        if not chunk:
            continue
        words = chunk.split()
        cur: list[str] = []
        for w in words:
            cur.append(w)
            stripped = w.rstrip(".!?…,\"')")
            if len(" ".join(cur)) >= 10 and stripped.endswith(_BREAK_AFTER):
                units.append(" ".join(cur))
                cur = []
        if cur:
            units.append(" ".join(cur))
    return units or [text.strip()]


def build_blocks(
    words: list[WordTiming], *, max_chars: int = 18, max_lines: int = 2,
    highlight_terms: list[str] | None = None, font_size: int = 48, animation: str = "pop",
) -> list[SubtitleBlock]:
    """Group word timings into on-screen blocks along phrase boundaries."""
    if not words:
        return []
    hl = {h.lower() for h in (highlight_terms or [])}
    text = " ".join(w.word for w in words)
    units = phrase_units(text)

    # map units back onto the word stream in order
    blocks: list[SubtitleBlock] = []
    wi = 0
    budget = max_chars * max_lines
    for unit in units:
        u_words = unit.split()
        # consume that many words from the stream (best-effort alignment)
        take = min(len(u_words), len(words) - wi)
        if take <= 0:
            break
        seg = words[wi:wi + take]
        wi += take
        # split an over-long unit into <=budget sub-blocks on word boundaries
        acc: list[WordTiming] = []
        for w in seg:
            if acc and len(" ".join(x.word for x in acc) + " " + w.word) > budget:
                blocks.append(_mk_block(acc, hl, font_size, max_lines, animation))
                acc = []
            acc.append(w)
        if acc:
            blocks.append(_mk_block(acc, hl, font_size, max_lines, animation))
    return blocks


def _mk_block(seg: list[WordTiming], hl: set[str], font_size: int,
              max_lines: int, animation: str) -> SubtitleBlock:
    text = " ".join(w.word for w in seg)
    highlights = []
    for w in seg:
        core = w.word.strip(".!?…,\"')")
        if _NUM_RE.search(core) or core.lower() in hl:
            highlights.append(core)
    return SubtitleBlock(
        start=round(seg[0].start, 3), end=round(seg[-1].end, 3), text=text,
        position="bottom", font_size=font_size, highlight_words=highlights[:3],
        animation=animation, max_lines=max_lines,
    )


# ---- writers ---------------------------------------------------------------- #

def _ts(t: float, sep: str = ",") -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write_srt(blocks: list[SubtitleBlock], path: str) -> str:
    lines = []
    for i, b in enumerate(blocks, 1):
        lines += [str(i), f"{_ts(b.start)} --> {_ts(b.end)}", b.text, ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def write_ass(blocks: list[SubtitleBlock], path: str, *, play_w: int, play_h: int) -> str:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default, Malgun Gothic, {max(28, play_h // 22)}, &H00FFFFFF, &H00101010, &H80000000, 0, 3, 0, 2, 60, 60, {int(play_h * 0.14)}
Style: HL, Malgun Gothic, {max(28, play_h // 22)}, &H0043D1FF, &H00101010, &H80000000, 1, 3, 0, 2, 60, 60, {int(play_h * 0.14)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for b in blocks:
        txt = b.text
        for h in b.highlight_words:
            txt = txt.replace(h, "{\\c&H0043D1FF&\\b1}" + h + "{\\c&H00FFFFFF&\\b0}")
        ev.append(f"Dialogue: 0,{_ts(b.start, '.')[:-1]},{_ts(b.end, '.')[:-1]},Default,,0,0,0,,{txt}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(ev) + "\n")
    return path


def write_ass_kinetic(blocks: list[SubtitleBlock], path: str, *, play_w: int, play_h: int,
                      word_timings: list[WordTiming] | None = None) -> str:
    """ASS with per-word \\k karaoke reveal (Video Studio Upgrade B31).

    Additive alternative to `write_ass` — existing callers are untouched. Uses real
    per-word timings when supplied; otherwise distributes each block's duration
    evenly across its words (an honest approximation, not fake alignment).
    """
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Kinetic, Malgun Gothic, {max(30, play_h // 20)}, &H00FFFFFF, &H00AAAAAA, &H00101010, &H80000000, 1, 3, 0, 2, 60, 60, {int(play_h * 0.14)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    wt_by_word: list[WordTiming] = list(word_timings or [])
    wi = 0
    ev: list[str] = []
    for b in blocks:
        words = b.text.split()
        if not words:
            continue
        parts: list[str] = []
        if wt_by_word and wi + len(words) <= len(wt_by_word):
            seg = wt_by_word[wi:wi + len(words)]
            wi += len(words)
            for w in seg:
                cs = max(1, int(round((w.end - w.start) * 100)))
                parts.append(f"{{\\k{cs}}}{w.word}")
        else:
            per = max(1, int(round((b.end - b.start) * 100 / len(words))))
            for w in words:
                parts.append(f"{{\\k{per}}}{w}")
        ev.append(f"Dialogue: 0,{_ts(b.start, '.')[:-1]},{_ts(b.end, '.')[:-1]},Kinetic,,0,0,0,,"
                  + " ".join(parts))
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(ev) + "\n")
    return path


def write_renderer_json(blocks: list[SubtitleBlock], path: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([b.model_dump() for b in blocks], f, ensure_ascii=False, indent=2)
    return path


# ---- Pillow overlay (libass-free burn-in path) ---------------------------- #

@dataclass
class OverlayPNG:
    path: str
    start: float
    end: float


def render_overlays(blocks: list[SubtitleBlock], *, width: int, height: int,
                    out_dir: str, style: str = "CLEAN") -> list[OverlayPNG]:
    from pathlib import Path

    from PIL import Image, ImageDraw

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    accent = (67, 209, 255)
    out: list[OverlayPNG] = []
    for i, b in enumerate(blocks):
        fs = max(28, min(b.font_size, width // 16))
        font = load_font(fs)
        bold = load_font(fs, bold=True)
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        max_w = int(width * 0.86)
        lines = wrap_by_width(d, b.text, font, max_w)[: b.max_lines]
        line_h = int(fs * 1.34)
        block_h = line_h * len(lines)
        y0 = int(height * 0.80) - block_h if b.position == "bottom" else int(height * 0.12)
        # translucent plate
        pad = int(fs * 0.5)
        plate_w = max((d.textlength(ln, font=font) for ln in lines), default=0) + pad * 2
        x_plate = (width - plate_w) / 2
        d.rectangle([x_plate, y0 - pad, x_plate + plate_w, y0 + block_h + pad],
                    fill=(10, 10, 12, 150))
        y = y0
        hl = {h for h in b.highlight_words}
        for ln in lines:
            total = d.textlength(ln, font=font)
            x = (width - total) / 2
            for tok in ln.split(" "):
                core = tok.strip(".!?…,\"')")
                is_hl = core in hl
                f_ = bold if is_hl else font
                col = accent if is_hl else (245, 245, 245)
                d.text((x, y), tok, font=f_, fill=col, stroke_width=3, stroke_fill=(8, 8, 8))
                x += d.textlength(tok + " ", font=f_)
            y += line_h
        p = str(Path(out_dir) / f"sub_{i:03d}.png")
        img.save(p, "PNG")
        out.append(OverlayPNG(path=p, start=b.start, end=b.end))
    return out
