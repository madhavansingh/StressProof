"""
Canonical JSON serialization and strict verification.
Matches Section 7.1 of implementationplan.md.
"""

import json
from typing import Any

from .constants import MAX_SAFE_INT


def _assert_canonical_types(obj: Any) -> None:
    """Recursively verify that only canonical value types exist."""
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return
    if isinstance(obj, float):
        raise TypeError("Floats are strictly prohibited in canonical JSON")
    if isinstance(obj, int):
        if not -MAX_SAFE_INT < obj < MAX_SAFE_INT:
            raise ValueError(
                f"Integer {obj} is outside the JSON-safe range (|v| < 2**53); use a decimal string"
            )
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"Dictionary keys must be strings, got {type(k)}")
            _assert_canonical_types(v)
        return
    if isinstance(obj, list):
        for item in obj:
            _assert_canonical_types(item)
        return
    raise TypeError(f"Type {type(obj)} is not allowed in canonical JSON")


def canonical_bytes(obj: Any) -> bytes:
    """
    Serializes an object into deterministic canonical UTF-8 bytes.
    Rules:
    - Keys sorted by Unicode code point
    - Separators (',', ':') without spaces
    - ensure_ascii=True (non-ASCII escaped as \\uXXXX)
    - Floats, tuples, sets, bytes and integers with |v| >= 2**53 rejected
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


def _reject_float(value: str) -> Any:
    raise ValueError(f"Floats are strictly prohibited in canonical JSON: {value}")


def _reject_constant(value: str) -> Any:
    raise ValueError(f"Non-finite number {value} is not allowed in canonical JSON")


def parse_strict(b: bytes) -> Any:
    """
    Parses canonical JSON bytes and verifies that re-serializing reproduces the exact input bytes.
    Raises ValueError for anything that is not canonical JSON (including floats, NaN, a BOM,
    duplicate keys, whitespace, or key reordering).
    """
    if not isinstance(b, (bytes, bytearray)):
        raise TypeError(f"Expected bytes, got {type(b)}")
    b = bytes(b)
    try:
        text = b.decode("utf-8", errors="strict")
        parsed = json.loads(text, parse_float=_reject_float, parse_constant=_reject_constant)
        re_serialized = canonical_bytes(parsed)
    except (UnicodeDecodeError, TypeError, ValueError, RecursionError) as e:
        raise ValueError(f"Not canonical JSON: {e}") from e
    if re_serialized != b:
        raise ValueError("JSON bytes are not canonical")
    return parsed
