"""
Golden fixture generator (implementationplan.md Appendix A, "Two uses of these numbers").

Rebuilds data/fixtures/casefile_v1.json from fixed inputs. The committed fixture is the
team's golden reference (frontend and e2e pin its hash), so this script never changes its
bytes: if the rebuilt case file differs from the committed one, it stops with an error.

Usage:
    uv run -m stressproof_pipeline.fixtures          # verify only (default)
    uv run -m stressproof_pipeline.fixtures --write  # verify, then write the derived files
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from stressproof_core.canonical_json import canonical_bytes
from stressproof_core.hashing import keccak256_hex
from stressproof_core.report import build_case_file

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "data" / "fixtures"

DATASET_ID = "weth-stable-fixture-v1"
MARKET_ID_STRING = "aave-v3-eth-weth-stable"
SHOCK_BPS = -3000
RATIONALE = "Phase 1 fixed scenario: -3000 bps WETH shock."
REPLAYER_COMMIT = "0" * 40

EXPECTED_RESULTS = {
    "debtAtRiskUsd8": "3374300000002",
    "liquidatableAccounts": 4,
    "liquidationVolumeUsd8": "3174300000001",
    "residualBadDebtUsd8": "200000000001",
}

# Appendix A accounts, same order and amounts, with synthetic ids.
_ACCOUNTS: List[Tuple[str, str]] = [
    ("10000000000000000000", "2000000000000"),
    ("5000000000000000000", "1200000000000"),
    ("10000000000000000000", "1000000000000"),
    ("1000000000000000000", "174300000000"),
    ("1000000000000000000", "174300000001"),
    ("1", "1"),
]


def build_snapshot() -> Dict:
    return {
        "accounts": [
            {
                "collateralAmount": collateral,
                "debtUsd8": debt,
                "id": f"synth-{i:04d}",
                "origin": "synthetic",
            }
            for i, (collateral, debt) in enumerate(_ACCOUNTS, start=1)
        ],
        "assets": {
            "WETH": {"bonusBps": 10500, "decimals": 18, "ltBps": 8300, "priceUsd8": "300000000000"},
        },
    }


def build_manifest(snapshot_hash: str) -> Dict:
    # Values match the committed fixture (data/fixtures/casefile_v1.json), not a real extraction.
    return {
        "counts": {"real": 0, "synthetic": len(_ACCOUNTS)},
        "dataClass": "SYNTHETIC",
        "dataProviderAddress": "0x0000000000000000000000000000000000000002",
        "datasetId": DATASET_ID,
        "excludedCounts": {
            "eMode": 0,
            "noDebt": 0,
            "nonStableDebt": 0,
            "nonWethCollateral": 0,
            "other": 0,
            "wethNotCollateral": 0,
        },
        "extractedAt": "2026-10-28T00:00:00Z",
        "extractionScriptCommit": "0" * 40,
        "filter": "collateral=WETH only; debt=stablecoins; eMode=0; isolation=false",
        "forkBlock": 19000000,
        "forkBlockHash": "0x" + "0" * 64,
        "forkBlockTimestamp": 1700000000,
        "network": "ethereum-mainnet-fork",
        "oracleAddress": "0x0000000000000000000000000000000000000003",
        "poolAddress": "0x0000000000000000000000000000000000000004",
        "poolAddressesProvider": "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e",
        "rpcProvider": "Fixture",
        "snapshotHash": snapshot_hash,
        "stablecoinAllowlist": [
            {"address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "symbol": "USDC"},
        ],
        "syntheticSeed": 42,
        "wethAddress": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    }


def build_fixture() -> Dict[str, bytes]:
    """Return {relative path under data/fixtures: exact bytes} for every fixture file."""
    snapshot = build_snapshot()
    snapshot_bytes = canonical_bytes(snapshot)
    manifest = build_manifest(keccak256_hex(snapshot_bytes))
    manifest_bytes = canonical_bytes(manifest)

    case_file = build_case_file(
        snapshot=snapshot,
        manifest=manifest,
        scenario={"asset": "WETH", "shockBps": SHOCK_BPS},
        rationale=RATIONALE,
        replayer_commit=REPLAYER_COMMIT,
        market_id_string=MARKET_ID_STRING,
    )
    if case_file["results"] != EXPECTED_RESULTS:
        raise AssertionError(f"replay drifted from Appendix A: {case_file['results']}")
    case_bytes = canonical_bytes(case_file)

    return {
        "casefile_v1.json": case_bytes,
        "casefile_v1.keccak": (keccak256_hex(case_bytes) + "\n").encode("ascii"),
        "snapshot_v1.json": snapshot_bytes,
        "dataset_manifest_v1.json": manifest_bytes,
        f"datasets/{DATASET_ID}/snapshot.json": snapshot_bytes,
        f"datasets/{DATASET_ID}/dataset_manifest.json": manifest_bytes,
    }


# The golden files are verified but never rewritten by this script.
GOLDEN = ("casefile_v1.json", "casefile_v1.keccak")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--write", action="store_true", help="write the derived fixture files")
    parser.add_argument("--dir", type=Path, default=FIXTURES_DIR, help="fixtures directory")
    args = parser.parse_args(argv)

    files = build_fixture()
    ok = True
    for name in GOLDEN:
        path = args.dir / name
        if not path.exists():
            print(f"MISSING  {path}", file=sys.stderr)
            ok = False
        elif path.read_bytes() != files[name]:
            print(f"DIFFERS  {path}: rebuilt bytes do not match the committed golden file", file=sys.stderr)
            ok = False
    if not ok:
        print("Refusing to continue: the golden fixture must not change without team approval.", file=sys.stderr)
        return 1

    for name, data in files.items():
        if name in GOLDEN:
            continue
        path = args.dir / name
        current = path.read_bytes() if path.exists() else None
        if current == data:
            status = "same"
        elif args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            status = "written"
        else:
            status = "missing" if current is None else "stale"
            ok = False
        print(f"{status:8} {path.relative_to(args.dir)}")

    print(f"evidenceHash  {keccak256_hex(files['casefile_v1.json'])}")
    print(f"snapshotHash  {keccak256_hex(files['snapshot_v1.json'])}")
    if not ok:
        print("Derived files are missing or stale; re-run with --write.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
