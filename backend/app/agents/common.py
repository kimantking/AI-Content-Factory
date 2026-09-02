from __future__ import annotations

import json
from typing import Any

from app.db.models import (
    Campaign,
    Hook,
    ResearchSource,
    Strategy,
    VerifiedFact,
)
from app.providers.errors import InvalidOutputError


def _extract_json_blob(text: str) -> str:
    """Best-effort: pull the JSON object/array out of an LLM reply that wrapped it
    in prose or a ```json fence. A clean JSON string is returned unchanged, so
    this is a no-op for well-behaved providers (the mock) and only kicks in for
    real adapters that add chatter. Idea borrowed from `instructor` / `outlines`
    (no dependency added)."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        s = s.strip()
        if s[:4].lower() == "json":
            s = s[4:].lstrip()
    if s[:1] in "{[":
        return s
    starts = [i for i in (s.find("{"), s.find("[")) if i != -1]
    if not starts:
        return s
    start = min(starts)
    open_ch = s[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return s[start:]


def parse_json(text: str, *, task: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return json.loads(_extract_json_blob(text))
    except ValueError as e:
        raise InvalidOutputError(f"invalid JSON from LLM (task={task}): {e}") from e


def set_step(session, campaign_id: str, step: str, status: str = "RUNNING") -> None:
    camp = session.get(Campaign, campaign_id)
    if camp:
        camp.current_step = step
        camp.status = status


def replace_sources(session, campaign_id: str, items) -> list[dict]:
    session.query(ResearchSource).filter_by(campaign_id=campaign_id).delete()
    session.flush()
    out = []
    for it in items:
        row = ResearchSource(
            campaign_id=campaign_id, url=it.url, title=it.title,
            snippet=it.snippet, published_at=it.published_at,
        )
        session.add(row)
        session.flush()
        out.append({
            "id": row.id, "url": row.url, "title": row.title,
            "snippet": row.snippet, "published_at": row.published_at,
        })
    return out


def replace_facts(session, campaign_id: str, facts: list[dict]) -> None:
    session.query(VerifiedFact).filter_by(campaign_id=campaign_id).delete()
    session.flush()
    for f in facts:
        session.add(VerifiedFact(
            campaign_id=campaign_id, fact=f["fact"], status=f["status"],
            confidence=float(f.get("confidence", 0.0)),
            source_ids=f.get("source_ids", []), reason=f.get("reason", ""),
        ))
    session.flush()


def replace_strategy(session, campaign_id: str, data: dict) -> None:
    session.query(Strategy).filter_by(campaign_id=campaign_id).delete()
    session.flush()
    session.add(Strategy(
        campaign_id=campaign_id, angle=data["angle"], key_message=data["key_message"],
        tone=data.get("tone", ""), target_emotion=data.get("target_emotion", ""),
        payload=data,
    ))
    session.flush()


def replace_hooks(session, campaign_id: str, hooks: list[dict]) -> None:
    session.query(Hook).filter_by(campaign_id=campaign_id).delete()
    session.flush()
    for rank, h in enumerate(sorted(hooks, key=lambda x: x.get("score", 0), reverse=True)):
        session.add(Hook(
            campaign_id=campaign_id, text=h["text"], style=h.get("style", ""),
            score=float(h.get("score", 0.0)), rank=rank,
        ))
    session.flush()
