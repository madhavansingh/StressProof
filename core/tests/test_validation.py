"""
Tests for evidence validation rules V-01..V-14.
"""

from pathlib import Path

from stressproof_core.canonical_json import canonical_bytes
from stressproof_core.hashing import keccak256_hex
from stressproof_core.validation import validate


def test_validation_empty_bytes():
    v = validate(b"")
    assert any(violation.code == "V-01" for violation in v)


def test_validation_hash_mismatch():
    raw = b'{"hello":"world"}'
    v = validate(raw, onchain={"evidenceHash": "0x0000000000000000000000000000000000000000000000000000000000000000"})
    assert any(violation.code == "V-02" for violation in v)


def test_validation_canonical_fixture():
    b = (Path(__file__).resolve().parents[2] / "data" / "fixtures" / "casefile_v1.json").read_bytes()

    expected_hash = keccak256_hex(b)
    # Validate with matching hash and marketId
    v = validate(
        b,
        onchain={
            "evidenceHash": expected_hash,
            "marketId": keccak256_hex(b"aave-v3-eth-weth-stable"),
            "claimedResidualBadDebt": 200000000001,
        },
    )
    # The golden fixture carries the real snapshotHash, so every rule passes.
    assert v == []
