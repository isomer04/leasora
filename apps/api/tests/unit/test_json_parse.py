"""Tests for the shared JSON-parsing helper.

The helper was extracted from three near-duplicated call sites, so a 
regression in it would break every LLM caller. Covers fence stripping with 
case variations, leading/trailing whitespace, in-place failures, and 
JSON-parsing-null contract.
"""

from __future__ import annotations

import json

from leasora_api.core.json_parse import parse_json_lenient, strip_code_fence


def test_strip_code_fence_lowercase_json() -> None:
    body = '{"answer": "yes"}'
    wrapped = f"```json\n{body}\n```"
    assert strip_code_fence(wrapped) == body


def test_strip_code_fence_uppercase_json() -> None:
    """Opening tag casing must not affect stripping."""
    body = '{"answer": "yes"}'
    wrapped = f"```JSON\n{body}\n```"
    assert strip_code_fence(wrapped) == body, "Fence stripping must be case-insensitive"


def test_strip_code_fence_no_language() -> None:
    body = '{"a": 1}'
    wrapped = f"```\n{body}\n```"
    assert strip_code_fence(wrapped) == body


def test_strip_code_fence_passthrough_when_unfenced() -> None:
    """Plain JSON should be returned (modulo outer whitespace) intact."""
    assert strip_code_fence('  {"a": 1}  ') == '{"a": 1}'


def test_strip_code_fence_preserves_inner_whitespace() -> None:
    body = '{"a": 1, "b": [1, 2]}'
    wrapped = f"```json\n{body}\n```"
    assert json.loads(strip_code_fence(wrapped)) == json.loads(body)


def test_parse_json_lenient_direct() -> None:
    assert parse_json_lenient('{"a": 1}') == {"a": 1}


def test_parse_json_lenient_with_fence() -> None:
    assert parse_json_lenient('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_lenient_returns_none_on_garbage() -> None:
    assert parse_json_lenient("not json at all") is None


def test_parse_json_lenient_returns_none_on_unfenced_garbage() -> None:
    assert parse_json_lenient("this is plain prose, not JSON") is None
