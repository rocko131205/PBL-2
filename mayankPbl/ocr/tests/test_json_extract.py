"""V3 — robust LLM JSON extractor tests."""
from src.agent_workflow import _extract_json


def test_direct_object():
    assert _extract_json('{"a": 1}') == {"a": 1}

def test_fenced_json():
    assert _extract_json('```json\n{"a": 2}\n```') == {"a": 2}

def test_fenced_no_lang():
    assert _extract_json('```\n[1, 2, 3]\n```') == [1, 2, 3]

def test_prose_wrapped_object():
    assert _extract_json('Here is the result: {"grade": "A"} hope that helps') == {"grade": "A"}

def test_array_in_prose():
    assert _extract_json('The peers are ["CRM", "NOW"] as requested') == ["CRM", "NOW"]

def test_garbage_returns_none():
    assert _extract_json("no json here at all") is None

def test_empty():
    assert _extract_json("") is None
    assert _extract_json(None) is None
