"""
Hashing and canonical JSON catalogue: T-P-01, T-P-02, T-P-10..T-P-14 (implementationplan.md §21.3).
"""

import hashlib
import json
from pathlib import Path

import pytest

from stressproof_core import canonical_bytes, keccak256_hex, market_id, parse_strict

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "casefile_v1.json"

KECCAK_EMPTY = "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
MARKET_ID_HEX = "0x2701f07d2eb0de529ccb283ac9cd1ebb8ed772916b7db0822335d9bcdabbc026"


# --- T-P-01 / T-P-02 -----------------------------------------------------------

def test_tp01_keccak_empty_is_not_nist_sha3():
    assert keccak256_hex(b"") == KECCAK_EMPTY
    assert keccak256_hex(b"") != "0x" + hashlib.sha3_256(b"").hexdigest()


def test_tp02_market_id_pinned():
    assert market_id("aave-v3-eth-weth-stable") == MARKET_ID_HEX


# --- T-P-10 ----------------------------------------------------------------------

def test_tp10_fixture_bytes_are_their_own_canonical_form():
    raw = FIXTURE.read_bytes()
    assert canonical_bytes(json.loads(raw)) == raw
    assert canonical_bytes(parse_strict(raw)) == raw


# --- T-P-11 ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "obj",
    [
        1.5,
        {"a": {"b": [1, {"c": 0.0}]}},
        [1, 2, [3, [4, float("nan")]]],
        {"a": float("inf")},
    ],
)
def test_tp11_float_anywhere_raises(obj):
    with pytest.raises(TypeError, match="Floats are strictly prohibited"):
        canonical_bytes(obj)


@pytest.mark.parametrize("obj", [(1, 2), {"a": (1,)}, {1, 2}, frozenset([1]), b"x", {"a": bytearray(b"x")}, {1: "a"}])
def test_tp11_disallowed_container_types_raise(obj):
    with pytest.raises(TypeError):
        canonical_bytes(obj)


@pytest.mark.parametrize("value", [2**53, -(2**53), 2**60 + 7, 10**27])
def test_tp11_unsafe_json_numbers_raise(value):
    with pytest.raises(ValueError, match="JSON-safe range"):
        canonical_bytes({"nested": [value]})


def test_tp11_largest_safe_integers_pass():
    assert canonical_bytes([2**53 - 1, -(2**53 - 1)]) == b"[9007199254740991,-9007199254740991]"


def test_tp11_bool_and_null_are_allowed():
    assert canonical_bytes({"t": True, "f": False, "n": None}) == b'{"f":false,"n":null,"t":true}'


# --- T-P-12 ----------------------------------------------------------------------

def test_tp12_key_order_and_whitespace_variants_are_identical():
    variants = [
        '{"b":{"y":2,"x":1},"a":[3,{"q":1,"p":2}]}',
        '{ "a" : [ 3 , { "p" : 2 , "q" : 1 } ] , "b" : { "x" : 1 , "y" : 2 } }',
        '{\n  "b": {"x": 1, "y": 2},\n  "a": [3, {"q": 1, "p": 2}]\n}\n',
    ]
    out = {canonical_bytes(json.loads(v)) for v in variants}
    assert out == {b'{"a":[3,{"p":2,"q":1}],"b":{"x":1,"y":2}}'}


# --- T-P-13 ----------------------------------------------------------------------

def test_tp13_non_ascii_is_escaped_deterministically():
    obj = {"agentRationale": "ETH ↓ 30% — café \U0001F4C9"}
    first = canonical_bytes(obj)
    assert first == canonical_bytes(json.loads(first))
    assert first == canonical_bytes(dict(obj))
    assert first.isascii()
    assert b"\\u2193" in first and b"\\u2014" in first and b"\\u00e9" in first
    assert b"\\ud83d\\udcc9" in first  # astral characters become a surrogate pair
    assert parse_strict(first) == obj


# --- T-P-14 ----------------------------------------------------------------------

CANONICAL = b'{"a":1,"b":"x"}'


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a": 1,"b":"x"}',            # extra space
        b'{"a":1,"b":"x"}\n',           # trailing newline
        b"\xef\xbb\xbf" + CANONICAL,    # UTF-8 BOM
        b'{"b":"x","a":1}',             # reordered keys
        b'{"a":1,"a":1,"b":"x"}',       # duplicate key
        b'{"a":1.0,"b":"x"}',           # float
        b'{"a":NaN,"b":"x"}',           # non-finite
        b'{"a":1,"b":"\xe9"}',          # raw non-ASCII instead of \u escape
        b"\xff",                        # invalid UTF-8
    ],
)
def test_tp14_parse_strict_rejects_non_canonical(raw):
    with pytest.raises(ValueError):
        parse_strict(raw)


def test_tp14_parse_strict_accepts_canonical():
    assert parse_strict(CANONICAL) == {"a": 1, "b": "x"}
