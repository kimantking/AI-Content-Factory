from __future__ import annotations

import pytest

from app.agents.common import _extract_json_blob, parse_json
from app.agents.nodes import _FIX_QUERY_ANGLES, _fix_query
from app.providers.errors import InvalidOutputError


# ---- parse_json robustness (instructor/outlines-style extraction) ---------- #

def test_parse_json_passes_clean_json_through():
    assert parse_json('{"a": 1, "b": [2, 3]}', task="t") == {"a": 1, "b": [2, 3]}


def test_parse_json_strips_markdown_fence():
    raw = '```json\n{"body": "hi"}\n```'
    assert parse_json(raw, task="t") == {"body": "hi"}


def test_parse_json_extracts_object_from_prose():
    raw = 'Sure! Here is the result:\n{"x": {"y": 1}}\nHope that helps.'
    assert parse_json(raw, task="t") == {"x": {"y": 1}}


def test_parse_json_handles_braces_inside_strings():
    raw = 'noise {"note": "a } b { c", "n": 1} trailing'
    assert parse_json(raw, task="t") == {"note": "a } b { c", "n": 1}


def test_parse_json_still_raises_on_garbage():
    with pytest.raises(InvalidOutputError):
        parse_json("not json at all", task="t")


def test_extract_json_blob_array():
    assert _extract_json_blob('prefix [1, 2, 3] suffix') == "[1, 2, 3]"


# ---- research fix-pass query variation ------------------------------------ #

def test_fix_query_rotates_by_round_and_mentions_topic():
    topic = "AI 일자리"
    seen = {_fix_query(topic, r) for r in (1, 2, 3)}
    assert len(seen) == len(_FIX_QUERY_ANGLES)  # each round a distinct angle
    assert all(topic in q for q in seen)
    # wraps around, stays deterministic
    assert _fix_query(topic, 4) == _fix_query(topic, 1)
