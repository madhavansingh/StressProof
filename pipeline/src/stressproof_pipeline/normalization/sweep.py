"""
Shock sweep: pick the Phase 1 scenario and the honest residual R that sets the vault thresholds.
Matches implementationplan.md §9.8, §12.5 and C-13.

    uv run -m stressproof_pipeline.normalization.sweep --dataset <id>

A shock qualifies if residual bad debt > 0 AND at least two accounts are liquidatable.
If -3000 qualifies it is chosen (the spec's example); otherwise the smallest-magnitude
qualifying shock. LTV_THRESHOLD = R // 2, PAUSE_THRESHOLD = 2 * R. Nothing is ever inflated.

Stale output policy: sweep.json is written only by a successful run. If a run fails (bad
inputs, no qualifying shock, or LTV_THRESHOLD == 0) and an earlier sweep.json exists, it is
moved to sweep.stale.json, never deleted. sweep.json therefore always belongs to the last
successful run on the current snapshot, and every sweep.json carries the snapshotHash it was
computed from, so consumers can also check it against dataset_manifest.json.
"""

import argparse
import os
import sys
from typing import Dict, List, Optional

from stressproof_core.hashing import keccak256_hex
from stressproof_core.replay import replay

from ..datafiles import PipelineError, check_manifest, check_snapshot, read_canonical, write_canonical
from ..paths import MANIFEST, SNAPSHOT, SWEEP, dataset_dir, load_env

STALE_SWEEP = "sweep.stale.json"

SHOCKS = list(range(-1000, -9001, -500))     # -1000, -1500, ..., -9000
PREFERRED_SHOCK = -3000
MIN_LIQUIDATABLE = 2
READABLE_R_USD8 = 1000 * 10**8               # §12.5: under $1,000, say so plainly
SELECTION_RULE = ("qualifies: residualBadDebt > 0 and liquidatableAccounts >= 2; "
                  "choose -3000 if it qualifies, else the smallest-magnitude qualifying shock")


def sweep_table(snapshot: dict, shocks: List[int] = SHOCKS) -> List[Dict]:
    rows = []
    for shock in shocks:
        r = replay({"scenario": {"asset": "WETH", "shockBps": shock}, "snapshot": snapshot})
        rows.append({
            "debtAtRiskUsd8": str(r.debt_at_risk_usd8),
            "liquidatableAccounts": r.liquidatable_accounts,
            "liquidationVolumeUsd8": str(r.liquidation_volume_usd8),
            "qualifies": r.residual_bad_debt_usd8 > 0 and r.liquidatable_accounts >= MIN_LIQUIDATABLE,
            "residualBadDebtUsd8": str(r.residual_bad_debt_usd8),
            "shockBps": shock,
        })
    return rows


def select_shock(rows: List[Dict]) -> Optional[Dict]:
    qualifying = [row for row in rows if row["qualifies"]]
    for row in qualifying:
        if row["shockBps"] == PREFERRED_SHOCK:
            return row
    return min(qualifying, key=lambda row: abs(row["shockBps"]), default=None)


def thresholds_for(r: int) -> Dict[str, str]:
    return {"ltvThresholdUsd8": str(r // 2), "pauseThresholdUsd8": str(2 * r)}


def run_shock_sweep(snapshot: dict) -> Dict:
    """In-memory sweep: table, chosen row (or None), R and thresholds."""
    rows = sweep_table(snapshot)
    chosen = select_shock(rows)
    result = {"chosen": chosen, "table": rows}
    if chosen is not None:
        r = int(chosen["residualBadDebtUsd8"])
        result["R"] = r
        result["thresholds"] = thresholds_for(r)
    return result


def _usd(usd8: str) -> str:
    whole, frac = divmod(int(usd8), 10**8)
    return f"${whole:,}.{frac // 10**6:02d}"


def format_table(rows: List[Dict], chosen: Optional[Dict]) -> str:
    header = f"{'shockBps':>9} {'liquidatable':>12} {'debtAtRisk':>22} {'liquidationVolume':>22} {'residualBadDebt':>22}  qualifies"
    lines = [header, "-" * len(header)]
    for row in rows:
        mark = "  <- chosen" if chosen is not None and row["shockBps"] == chosen["shockBps"] else ""
        lines.append(
            f"{row['shockBps']:>9} {row['liquidatableAccounts']:>12} {_usd(row['debtAtRiskUsd8']):>22} "
            f"{_usd(row['liquidationVolumeUsd8']):>22} {_usd(row['residualBadDebtUsd8']):>22}  "
            f"{'yes' if row['qualifies'] else 'no'}{mark}"
        )
    return "\n".join(lines)


def run(dataset_id: str) -> Dict:
    out = dataset_dir(dataset_id)
    try:
        return _run(dataset_id, out)
    except PipelineError as e:
        stale = _retire_stale_sweep(out)
        if stale:
            raise PipelineError(f"{e} (previous {SWEEP} moved to {STALE_SWEEP}; it does not describe this run)") from None
        raise


def _retire_stale_sweep(out) -> bool:
    current = out / SWEEP
    if not current.exists():
        return False
    current.replace(out / STALE_SWEEP)
    return True


def _run(dataset_id: str, out) -> Dict:
    snapshot_path = out / SNAPSHOT
    try:
        snapshot_bytes = snapshot_path.read_bytes()
    except FileNotFoundError:
        raise PipelineError(f"missing {snapshot_path}; run normalize first") from None
    manifest = check_manifest(read_canonical(out / MANIFEST), MANIFEST, final=True)
    snapshot_hash = keccak256_hex(snapshot_bytes)
    if snapshot_hash != manifest["snapshotHash"]:
        raise PipelineError(f"snapshot.json hash {snapshot_hash} != manifest snapshotHash {manifest['snapshotHash']}")
    snapshot = check_snapshot(read_canonical(snapshot_path), SNAPSHOT)

    result = run_shock_sweep(snapshot)
    rows, chosen = result["table"], result["chosen"]
    print(f"dataset {dataset_id} ({manifest['dataClass']}, {len(snapshot['accounts'])} accounts)")
    print(format_table(rows, chosen))
    if chosen is None:
        raise PipelineError("no shock qualifies (needs residual > 0 and >= 2 liquidatable accounts); "
                            "the dataset cannot drive the demo. Nothing was inflated and no new sweep.json was written.")

    r = result["R"]
    thresholds = result["thresholds"]
    if int(thresholds["ltvThresholdUsd8"]) == 0:
        raise PipelineError(f"R = {r} is too small: LTV_THRESHOLD = R // 2 = 0, which the vault rejects (needs > 0)")
    if r < READABLE_R_USD8:
        print(f"note: R = {_usd(str(r))} is under $1,000. Kept as is (plan §12.5); do not inflate the shock.")

    sweep = {
        "chosenShockBps": chosen["shockBps"],
        "dataClass": manifest["dataClass"],
        "datasetId": dataset_id,
        "residualBadDebtUsd8": str(r),
        "rule": SELECTION_RULE,
        "snapshotHash": snapshot_hash,
        "table": rows,
        "thresholds": thresholds,
    }
    write_canonical(out / SWEEP, sweep)
    print(f"\nchosen shockBps {chosen['shockBps']}, R = {r} ({_usd(str(r))})")
    print(f"wrote {out / SWEEP}\n")
    print("# send to Developer 3 (.env)")
    print(f"FIXED_SCENARIO_SHOCK_BPS={chosen['shockBps']}")
    print(f"LTV_THRESHOLD_USD8={thresholds['ltvThresholdUsd8']}")
    print(f"PAUSE_THRESHOLD_USD8={thresholds['pauseThresholdUsd8']}")
    return sweep


def main(argv=None) -> int:
    load_env()
    p = argparse.ArgumentParser(description="Sweep shocks and choose the demo scenario and thresholds (plan §9.8, §12.5).")
    p.add_argument("--dataset", default=os.environ.get("DATASET_ID"), help="datasetId (default $DATASET_ID)")
    args = p.parse_args(argv)
    if not args.dataset:
        p.error("--dataset is required (or set DATASET_ID)")
    try:
        run(args.dataset)
    except (PipelineError, ValueError) as e:
        print(f"sweep: error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
