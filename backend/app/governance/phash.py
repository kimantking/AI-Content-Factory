"""Deterministic perceptual hashing (§21) — Pillow only, no new dependency.

Average-hash + difference-hash over an 8×8 (aHash) / 9×8 (dHash) greyscale
downscale. Robust to resize / mild compression / minor crop. Not a substitute for
a real CV fingerprint (that is an optional adapter), but enough to catch
"same image, re-encoded" in tests and prefiltering.
"""
from __future__ import annotations


def _gray_pixels(path: str, w: int, h: int) -> list[int] | None:
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None
    try:
        im = Image.open(path).convert("L").resize((w, h))
    except Exception:  # noqa: BLE001
        return None
    return list(im.getdata())


def average_hash(path: str, size: int = 8) -> str:
    px = _gray_pixels(path, size, size)
    if not px:
        return ""
    avg = sum(px) / len(px)
    bits = 0
    for i, p in enumerate(px):
        if p >= avg:
            bits |= 1 << i
    return f"{bits:0{size * size // 4}x}"


def difference_hash(path: str, size: int = 8) -> str:
    px = _gray_pixels(path, size + 1, size)
    if not px:
        return ""
    bits = 0
    idx = 0
    for row in range(size):
        base = row * (size + 1)
        for col in range(size):
            if px[base + col] > px[base + col + 1]:
                bits |= 1 << idx
            idx += 1
    return f"{bits:0{size * size // 4}x}"


def phash(path: str) -> str:
    """Combined a/d hash string 'a:<hex>|d:<hex>'."""
    a, d = average_hash(path), difference_hash(path)
    return f"a:{a}|d:{d}" if (a or d) else ""


def _hamming_hex(x: str, y: str) -> int:
    if not x or not y or len(x) != len(y):
        return 999
    return bin(int(x, 16) ^ int(y, 16)).count("1")


def similarity(ph1: str, ph2: str) -> float:
    """0..1 — 1.0 identical. Averages the a-hash and d-hash Hamming similarity."""
    if not ph1 or not ph2:
        return 0.0
    def parts(s):
        out = {}
        for chunk in s.split("|"):
            if ":" in chunk:
                k, v = chunk.split(":", 1)
                out[k] = v
        return out
    p1, p2 = parts(ph1), parts(ph2)
    sims = []
    for k in ("a", "d"):
        if k in p1 and k in p2 and p1[k] and p2[k] and len(p1[k]) == len(p2[k]):
            bits = len(p1[k]) * 4
            sims.append(1.0 - _hamming_hex(p1[k], p2[k]) / bits)
    return round(sum(sims) / len(sims), 4) if sims else 0.0
