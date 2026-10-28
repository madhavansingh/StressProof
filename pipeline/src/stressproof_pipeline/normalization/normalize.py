"""
Step 4: Normalize, sort, canonicalize, and hash dataset snapshot.
Matches implementationplan.md §9.6 (and GATE PIPE-1).

    uv run -m stressproof_pipeline.normalization.normalize --dataset <id> [--allow-dirty]

Reads <dataset>/assets.json, dataset_manifest.draft.json, real_accounts.jsonl and/or
synthetic_accounts.jsonl. Writes snapshot.json (exact canonical bytes) and dataset_manifest.json.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from stressproof_core.canonical_json import canonical_bytes
from stressproof_core.constants import ORIGIN_REAL, ORIGIN_SYNTHETIC
from stressproof_core.hashing import keccak256_hex
from stressproof_core.report import build_case_file
from stressproof_core.validation import validate

from ..datafiles import (
    MANIFEST_KEYS,
    PipelineError,
    check_account,
    check_assets,
    check_manifest,
    git_commit,
    read_canonical,
    read_jsonl,
    write_canonical,
)
from ..paths import (
    ASSETS,
    DRAFT_MANIFEST,
    MANIFEST,
    REAL_ACCOUNTS,
    SNAPSHOT,
    SYNTHETIC_ACCOUNTS,
    dataset_dir,
    load_env,
)

MIN_REAL_ACCOUNTS = 20          # PIPE-1 [DECISION]: below this, add synthetic accounts (MIXED)
GATE_SCENARIO = {"asset": "WETH", "shockBps": -3000}


def data_class_for(real_count: int, synthetic_count: int) -> str:
    if real_count and synthetic_count:
        return "MIXED"
    if real_count:
        return "REAL"
    if synthetic_count:
        return "SYNTHETIC"
    raise PipelineError("snapshot has no accounts")


def merge_accounts(real: List[dict], synthetic: List[dict]) -> Tuple[List[dict], int]:
    """Reject duplicate ids, drop collateralAmount == "0", sort by id. Returns (accounts, dropped_zero)."""
    seen = set()
    merged = []
    dropped = 0
    for acc in real + synthetic:
        if acc["id"] in seen:
            raise PipelineError(f"duplicate account id {acc['id']!r}")
        seen.add(acc["id"])
        if acc["collateralAmount"] == "0":
            dropped += 1
            continue
        merged.append(acc)
    merged.sort(key=lambda a: a["id"])
    return merged, dropped


def normalize_dataset(
    real_accounts: List[dict],
    synthetic_accounts: List[dict],
    assets: dict,
    manifest_draft: dict,
) -> Tuple[dict, bytes, str]:
    """
    In-memory core of step 4: merge, dedupe, drop zero collateral, sort by id, canonicalize.
    Returns (snapshot, snapshot_bytes, snapshot_hash).
    """
    accounts, _ = merge_accounts(list(real_accounts), list(synthetic_accounts))
    snapshot = {"accounts": accounts, "assets": assets}
    snapshot_bytes = canonical_bytes(snapshot)
    return snapshot, snapshot_bytes, keccak256_hex(snapshot_bytes)


def _load_accounts(path: Path, origin: str) -> List[dict]:
    if not path.exists():
        return []
    return [check_account(r, origin, f"{path.name}:{i}") for i, r in enumerate(read_jsonl(path), start=1)]


def _previous_manifest(path: Path) -> Optional[Dict]:
    """The manifest from an earlier run, or None if absent or unreadable (it is then rewritten)."""
    if not path.exists():
        return None
    try:
        return check_manifest(read_canonical(path), MANIFEST, final=True)
    except PipelineError as e:
        print(f"note: ignoring unreadable previous {MANIFEST} ({e}); it will be replaced")
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gate_case_file(snapshot: dict, manifest: dict) -> None:
    """PIPE-1: a case file built from this dataset must pass core validation with no violations."""
    case_file = build_case_file(snapshot, manifest, GATE_SCENARIO, "PIPE-1 gate", manifest["extractionScriptCommit"])
    violations = validate(canonical_bytes(case_file))
    if violations:
        details = "; ".join(f"{v.code} {v.message}" for v in violations[:5])
        raise PipelineError(f"dataset fails core validation: {details}")


def run(dataset_id: str, allow_dirty: bool, now: Optional[str] = None) -> Dict:
    out = dataset_dir(dataset_id)
    if not out.is_dir():
        raise PipelineError(f"dataset directory {out} does not exist; run pin/extract or synth first")
    commit = git_commit(allow_dirty)

    assets = check_assets(read_canonical(out / ASSETS), ASSETS)
    draft = check_manifest(read_canonical(out / DRAFT_MANIFEST), DRAFT_MANIFEST, final=False)
    if draft["datasetId"] != dataset_id:
        raise PipelineError(f"draft manifest datasetId {draft['datasetId']!r} != {dataset_id!r}")

    real = _load_accounts(out / REAL_ACCOUNTS, ORIGIN_REAL)
    synthetic = _load_accounts(out / SYNTHETIC_ACCOUNTS, ORIGIN_SYNTHETIC)
    if not real and not synthetic:
        raise PipelineError(f"no accounts: neither {REAL_ACCOUNTS} nor {SYNTHETIC_ACCOUNTS} has records")

    accounts, dropped_zero = merge_accounts(real, synthetic)
    if dropped_zero:
        print(f"dropped {dropped_zero} account(s) with collateralAmount == 0")
    snapshot = {"accounts": accounts, "assets": assets}
    snapshot_bytes = canonical_bytes(snapshot)
    snapshot_hash = keccak256_hex(snapshot_bytes)

    real_count = sum(1 for a in accounts if a["origin"] == ORIGIN_REAL)
    synthetic_count = len(accounts) - real_count
    data_class = data_class_for(real_count, synthetic_count)
    if data_class == "REAL" and real_count < MIN_REAL_ACCOUNTS:
        raise PipelineError(f"only {real_count} real accounts (< {MIN_REAL_ACCOUNTS}); add synthetic accounts "
                            f"with synth --dataset {dataset_id} to make this a MIXED dataset")
    if synthetic_count and draft["syntheticSeed"] is None:
        raise PipelineError("synthetic accounts present but the draft manifest has no syntheticSeed")

    manifest = dict(draft)
    excluded = dict(draft["excludedCounts"])
    excluded["other"] += dropped_zero
    manifest.update({
        "counts": {"real": real_count, "synthetic": synthetic_count},
        "dataClass": data_class,
        "excludedCounts": excluded,
        "extractionScriptCommit": commit,
        "snapshotHash": snapshot_hash,
    })

    # Keep extractedAt when nothing changed, so re-running gives byte-identical output (PIPE-1).
    previous_path = out / MANIFEST
    previous = _previous_manifest(previous_path)
    stable = previous is not None and {k: v for k, v in previous.items() if k != "extractedAt"} == \
        {k: v for k, v in manifest.items() if k != "extractedAt"}
    manifest["extractedAt"] = previous["extractedAt"] if stable else (now or _utc_now())

    check_manifest(manifest, MANIFEST, final=True)
    _gate_case_file(snapshot, manifest)

    write_canonical(out / SNAPSHOT, snapshot)
    write_canonical(previous_path, manifest)
    print(f"wrote {out / SNAPSHOT} ({len(snapshot_bytes)} bytes, {len(accounts)} accounts, {data_class})")
    print(f"wrote {previous_path}")
    print(f"snapshotHash {snapshot_hash}")
    return manifest


def main(argv=None) -> int:
    load_env()
    p = argparse.ArgumentParser(description="Normalize a dataset into snapshot.json and dataset_manifest.json (plan §9.6).")
    p.add_argument("--dataset", default=os.environ.get("DATASET_ID"), help="datasetId (default $DATASET_ID)")
    p.add_argument("--allow-dirty", action="store_true", help="run on a dirty git tree (commit recorded as <sha>-dirty)")
    args = p.parse_args(argv)
    if not args.dataset:
        p.error("--dataset is required (or set DATASET_ID)")
    try:
        run(args.dataset, args.allow_dirty)
    except (PipelineError, ValueError) as e:
        print(f"normalize: error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
