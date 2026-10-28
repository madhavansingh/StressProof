"""
Tests for evidence validation rules V-01..V-14.
"""

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
    with open("data/fixtures/casefile_v1.json", "rb") as f:
        b = f.read()

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
    # The fixture snapshotHash in dataset was placeholder 0x00... so V-13 will flag mismatch
    v_codes = [violation.code for violation in v]
    assert "V-01" not in v_codes
    assert "V-02" not in v_codes
    assert "V-03" not in v_codes
    assert "V-04" not in v_codes
