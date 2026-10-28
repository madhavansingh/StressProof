"""
Tests for canonical JSON serialization.
"""

import pytest
from stressproof_core.canonical_json import canonical_bytes, parse_strict


def test_canonical_sort_keys():
    obj = {"z": 1, "a": 2, "m": {"b": 3, "a": 4}}
    b = canonical_bytes(obj)
    assert b == b'{"a":2,"m":{"a":4,"b":3},"z":1}'


def test_floats_prohibited():
    with pytest.raises(TypeError, match="Floats are strictly prohibited"):
        canonical_bytes({"a": 1.5})


def test_parse_strict_valid():
    b = b'{"a":1,"b":"hello"}'
    parsed = parse_strict(b)
    assert parsed == {"a": 1, "b": "hello"}


def test_parse_strict_non_canonical_rejected():
    # Extra whitespace
    b = b'{"a": 1, "b": "hello"}'
    with pytest.raises(ValueError, match="JSON bytes are not canonical"):
        parse_strict(b)
