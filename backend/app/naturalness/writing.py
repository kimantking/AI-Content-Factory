from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.naturalness.slop import AISlopReport, score_ai_slop
from app.naturalness.voice import VoiceProfile

_SENT_SPLIT = re.compile(r"(?<=[.!?。…])\s+")
_NUM = re.compile(r"\d[\d,.%]*")
_CONNECTIVE_ALT = {
    "그리고": ["", "여기에", "이어서"],
    "하지만": ["", "그런데", "다만"],
    "또한": ["", "여기에 더해"],
    "따라서": ["", "그래서"],
    "그러나": ["", "그런데"],
}
_BANNED_OPENERS = [
    "안녕하세요 여러분", "안녕하세요", "오늘은", "지금부터 자세히 살펴보겠습니다",
    "이번 시간에는", "본격적으로",
]
_CLICHES = ["여러분은 어떻게 생각하시나요?", "여러분은 어떻게 생각하시나요", "결론적으로", "정리하자면"]


@dataclass
class NaturalWritingResult:
    text: str
    slop_before: AISlopReport
    slop_after: AISlopReport
    fact_preserved: bool
    changed: bool
    notes: list[str] = field(default_factory=list)


def _split_sentences(text: str) -> list[str]:
    out: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            out.append("")
            continue
        parts = _SENT_SPLIT.split(line.strip())
        out.extend(p for p in parts if p)
    return out


def _numbers(text: str) -> set[str]:
    return {m.group(0).rstrip(".,") for m in _NUM.finditer(text)}


def _facts_preserved(draft: str, out: str, usable: list[str], unusable: list[str]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    ok = True
    for f in usable:
        if f and f in draft and f not in out:
            ok = False
            notes.append(f"검증 사실이 재작성 중 유실됨: {f[:40]}")
    for f in unusable:
        if f and f in out and f not in draft:
            ok = False
            notes.append("미검증 사실이 재작성 중 유입됨")
    draft_nums, out_nums = _numbers(draft), _numbers(out)
    if not out_nums.issubset(draft_nums):
        ok = False
        notes.append(f"원문에 없던 숫자가 생성됨: {sorted(out_nums - draft_nums)}")
    if not draft_nums.issubset(out_nums):
        ok = False
        notes.append(f"원문 숫자가 유실됨: {sorted(draft_nums - out_nums)}")
    return ok, notes


def _dedupe_connectives(sentences: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for s in sentences:
        stripped = s.lstrip()
        replaced = s
        for conn, alts in _CONNECTIVE_ALT.items():
            if stripped.startswith(conn):
                seen[conn] = seen.get(conn, 0) + 1
                if seen[conn] >= 2:
                    alt = alts[(seen[conn]) % len(alts)]
                    rest = stripped[len(conn):].lstrip(" ,")
                    replaced = (alt + (" " if alt else "") + rest) if rest else alt
                break
        out.append(replaced)
    return out


def _vary_rhythm(sentences: list[str]) -> list[str]:
    """One deterministic pass: split the longest sentence at a comma, merge the
    two shortest adjacent non-empty sentences. Never introduces errors."""
    idxs = [i for i, s in enumerate(sentences) if s.strip()]
    if len(idxs) < 3:
        return sentences
    out = list(sentences)

    longest = max(idxs, key=lambda i: len(out[i].split()))
    sent = out[longest]
    if "," in sent and ":" not in sent and len(sent.split()) >= 16:
        head, _, tail = sent.partition(",")
        head, tail = head.strip(), tail.strip()
        # only split when BOTH halves stand on their own as clauses
        if len(head.split()) >= 6 and len(tail.split()) >= 6:
            if not head.endswith((".", "!", "?")):
                head += "."
            out[longest] = head + " " + (tail[0].upper() + tail[1:] if tail[0].isascii() else tail)

    idxs = [i for i, s in enumerate(out) if s.strip()]
    best_pair = None
    best_len = 999
    for a, b in zip(idxs, idxs[1:]):
        combined = len(out[a].split()) + len(out[b].split())
        if combined < best_len and combined <= 10:
            best_len = combined
            best_pair = (a, b)
    if best_pair:
        a, b = best_pair
        merged = out[a].rstrip(".!? ") + ", " + (out[b][0].lower() + out[b][1:] if out[b][:1].isascii() else out[b])
        out[a] = merged
        out[b] = ""
    return out


def _strip_banned(text: str) -> tuple[str, bool]:
    changed = False
    lines = text.split("\n")
    if lines:
        first = lines[0].strip()
        for op in _BANNED_OPENERS:
            if first.startswith(op):
                rest = first[len(op):].lstrip(" ,.-")
                lines[0] = rest
                changed = True
                break
    text = "\n".join(lines)
    for c in _CLICHES:
        if c in text:
            text = text.replace(c, "").replace("  ", " ")
            changed = True
    return text, changed


def natural_writing_pass(
    draft: str,
    *,
    voice: VoiceProfile,
    usable_facts: list[str] | None = None,
    unusable_facts: list[str] | None = None,
    llm=None,
    max_target: int = 20,
) -> NaturalWritingResult:
    """Draft -> Natural Writing -> Fact Preservation Check (Amendment §4).

    In MOCK mode this is a deterministic rhythm/opener/connective cleanup. With a
    real LLM adapter it delegates the rewrite, then still runs the fact check and
    reverts on failure. It never inserts typos, fake experience, or fake facts.
    """
    usable = usable_facts or []
    unusable = unusable_facts or []
    before = score_ai_slop(draft, max_target=max_target)
    notes: list[str] = []

    if llm is not None:
        try:
            import json

            resp = llm.complete(
                system=(
                    "You rewrite a draft script to read like a human editor wrote it: "
                    "varied sentence length, no template openers, no filler. "
                    "Preserve every fact and number exactly. Do not invent experiences. "
                    "Return JSON {\"body\": string}."
                ),
                user=json.dumps({"draft": draft, "voice": voice.to_dict(),
                                 "keep_facts": usable}, ensure_ascii=False),
                task="natural_writing",
                context={"voice": voice.to_dict()},
            )
            candidate = json.loads(resp.text).get("body", draft)
        except Exception as e:  # noqa: BLE001 - fall back to deterministic
            notes.append(f"LLM natural pass failed, used deterministic fallback: {e}")
            candidate = _deterministic(draft)
    else:
        candidate = _deterministic(draft)

    candidate = re.sub(r"\n{3,}", "\n\n", candidate).strip()
    preserved, fnotes = _facts_preserved(draft, candidate, usable, unusable)
    notes += fnotes

    if not preserved:
        after = score_ai_slop(draft, max_target=max_target)
        return NaturalWritingResult(
            text=draft, slop_before=before, slop_after=after,
            fact_preserved=False, changed=False,
            notes=notes + ["fact preservation 실패 → 원본 draft 유지"],
        )

    after = score_ai_slop(candidate, max_target=max_target)
    return NaturalWritingResult(
        text=candidate, slop_before=before, slop_after=after,
        fact_preserved=True, changed=(candidate != draft), notes=notes,
    )


def _deterministic(draft: str) -> str:
    text, _ = _strip_banned(draft)
    blocks = text.split("\n\n")
    new_blocks = []
    for block in blocks:
        if block.strip().startswith(("-", "*", "•")) or not block.strip():
            new_blocks.append(block)
            continue
        sents = _split_sentences(block)
        sents = _dedupe_connectives(sents)
        sents = _vary_rhythm(sents)
        new_blocks.append(" ".join(s for s in sents if s).strip())
    return "\n\n".join(b for b in new_blocks).strip()
