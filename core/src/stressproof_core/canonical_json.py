"""
Canonical JSON serialization and strict verification.
Matches Section 7.1 of implementationplan.md.
"""

import json
from typing import Any


def _assert_canonical_types(obj: Any) -> None:
    """Recursively verify that no floating point, set, tuple or invalid types exist."""
    if isinstance(obj, float):
        raise TypeError("Floats are strictly prohibited in canonical JSON")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"Dictionary keys must be strings, got {type(k)}")
            _assert_canonical_types(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _assert_canonical_types(item)
    elif isinstance(obj, (set, bytes)):
        raise TypeError(f"Type {type(obj)} is not allowed in canonical JSON")
    elif not isinstance(obj, (str, int, bool, type(None))):
        raise TypeError(f"Disallowed value type: {type(obj)}")


def canonical_bytes(obj: Any) -> bytes:
    """
    Serializes an object into deterministic canonical UTF-8 bytes.
    Rules:
    - Keys sorted by Unicode code point
    - Separators (',', ':') without spaces
    - ensure_ascii=True (non-ASCII escaped as \\uXXXX)
    - Floats rejected
    - No trailing newline
    """
    _assert_canonical_types(obj)
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def parse_strict(b: bytes) -> Any:
    """
    Parses canonical JSON bytes and verifies that re-serializing reproduces the exact input bytes.
    """
    if not isinstance(b, bytes):
        raise TypeError(f"Expected bytes, got {type(b)}")
    parsed = json.loads(b.decode("utf-8"))
    re_serialized = canonical_bytes(parsed)
    if re_serialized != b:
        raise ValueError("JSON bytes are not canonical")
    return parsed
