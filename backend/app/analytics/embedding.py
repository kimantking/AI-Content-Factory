from __future__ import annotations

import hashlib
import math
import re

_DIM = 24
_TOKEN = re.compile(r"[\w가-힣]+")

# Cheap, deterministic, offline "embedding" — a hashed bag-of-tokens vector. Good
# enough to cluster near-duplicate topics ("AI로 사라질 직업" ~ "인공지능이 대체할 일자리")
# via a shared vocabulary of stems. Swap for a real EmbeddingProvider later.
_SYN = {
    "인공지능": "ai", "ai": "ai", "직업": "job", "일자리": "job", "커리어": "job",
    "사라지": "vanish", "사라질": "vanish", "대체": "vanish", "없어지": "vanish",
    "없어질": "vanish", "줄어들": "vanish", "줄어드": "vanish",
    "자동화": "automation", "로봇": "automation", "전망": "outlook", "순위": "outlook",
}
# common Korean particles / trailing josa to strip so "AI로" ~ "AI"
_PARTICLES = ("으로서", "에서의", "으로", "에서", "에게", "까지", "부터", "이라는", "라는",
              "들이", "들을", "들", "은", "는", "이", "가", "을", "를", "에", "의", "로",
              "도", "만", "와", "과", "게", "께", "라", "야", "여", "한", "할", "될", "될까")


def _strip_particle(t: str) -> str:
    for p in _PARTICLES:
        if len(t) > len(p) + 1 and t.endswith(p):
            return t[: -len(p)]
    return t


def _norm_tokens(text: str) -> list[str]:
    out = []
    for raw in _TOKEN.findall(text.lower()):
        t = _strip_particle(raw)
        out.append(_SYN.get(t, _SYN.get(raw, t)))
    return out


def embed(text: str) -> list[float]:
    vec = [0.0] * _DIM
    toks = _norm_tokens(text)
    for t in toks:
        h = int(hashlib.sha256(t.encode()).hexdigest()[:8], 16)
        vec[h % _DIM] += 1.0
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / n, 5) for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def assign_cluster(text: str, existing: dict[str, list[float]], *, threshold: float = 0.6) -> tuple[str, list[float]]:
    """Return (cluster_id, embedding). Reuses the closest existing cluster centroid
    above the threshold, else mints a new cluster id from the dominant tokens."""
    vec = embed(text)
    best_id, best_sim = None, 0.0
    for cid, centroid in existing.items():
        s = cosine(vec, centroid)
        if s > best_sim:
            best_id, best_sim = cid, s
    if best_id and best_sim >= threshold:
        return best_id, vec
    stems = [t for t in _norm_tokens(text) if len(t) > 1][:3]
    new_id = "-".join(stems) or hashlib.sha256(text.encode()).hexdigest()[:8]
    return new_id, vec
