"""
Golden fixture pins (Part 2, implementationplan.md Appendix A).
The frontend and scripts/e2e_local.sh rely on these exact hashes.
"""

import json
from pathlib import Path

from stressproof_core import canonical_bytes, evaluate, keccak256_hex, market_id, parse_strict, validate

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
DEPLOYMENTS = Path(__file__).resolve().parents[2] / "deployments"

EVIDENCE_HASH = "0x7f427d2c66ff24dd70014a717706d17a25d0070d67c16f69cd1ae9f3777a25f0"
SNAPSHOT_HASH = "0x9df1899fbcae4e418753920e0d1bee59eed4cb3d0445d982cbc06807838e199d"
HONEST_R = 200000000001


def fixture_bytes() -> bytes:
    return (FIXTURES / "casefile_v1.json").read_bytes()


def onchain(claimed: int) -> dict:
    return {
        "evidenceHash": EVIDENCE_HASH,
        "marketId": keccak256_hex(b"aave-v3-eth-weth-stable"),
        "claimedResidualBadDebt": claimed,
    }


def test_pinned_evidence_hash():
    raw = fixture_bytes()
    assert keccak256_hex(raw) == EVIDENCE_HASH
    assert (FIXTURES / "casefile_v1.keccak").read_text().strip() == EVIDENCE_HASH
    assert not raw.endswith(b"\n")
    parse_strict(raw)


def test_pinned_snapshot_hash_and_derived_files():
    case_file = json.loads(fixture_bytes())
    snapshot_bytes = canonical_bytes(case_file["snapshot"])
    assert keccak256_hex(snapshot_bytes) == SNAPSHOT_HASH
    assert case_file["dataset"]["snapshotHash"] == SNAPSHOT_HASH

    manifest_bytes = canonical_bytes(case_file["dataset"])
    dataset_dir = FIXTURES / "datasets" / "weth-stable-fixture-v1"
    assert (FIXTURES / "snapshot_v1.json").read_bytes() == snapshot_bytes
    assert (dataset_dir / "snapshot.json").read_bytes() == snapshot_bytes
    assert (FIXTURES / "dataset_manifest_v1.json").read_bytes() == manifest_bytes
    assert (dataset_dir / "dataset_manifest.json").read_bytes() == manifest_bytes


def test_fixture_validates_cleanly():
    assert validate(fixture_bytes(), onchain(HONEST_R)) == []


def test_fixture_honest_claim_matches():
    ev = evaluate(fixture_bytes(), onchain(HONEST_R))
    assert ev.verdict == "MATCH"
    assert ev.recomputed.residual_bad_debt_usd8 == HONEST_R


def test_fixture_inflated_claim_is_wrong_result():
    ev = evaluate(fixture_bytes(), onchain(3 * HONEST_R))
    assert ev.verdict == "WRONG_RESULT"
    assert ev.counter_residual_usd8 == HONEST_R


def test_market_id_matches_local_deployment():
    deployment = json.loads((DEPLOYMENTS / "31337.json").read_text())
    assert market_id(deployment["marketIdString"]) == deployment["marketId"]
    assert market_id("aave-v3-eth-weth-stable") == deployment["marketId"]
