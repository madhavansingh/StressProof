"""
Step 3: Deterministic synthetic accounts generator.
Matches implementationplan.md §9.5.

    uv run -m stressproof_pipeline.normalization.synth --seed 42 --count 40 \
        [--dataset ID] [--price-usd8 N --lt-bps N --bonus-bps N]

Writes <dataset>/synthetic_accounts.jsonl. When the dataset has no real data yet (no
assets.json from the pin step), it also writes assets.json and a SYNTHETIC draft manifest.
When real data exists, it reuses that asset configuration and records the seed in the draft.
"""

import argparse
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional

from stressproof_core.constants import BPS, EXPECTED_DECIMALS, MAX_LT_BPS, ORIGIN_SYNTHETIC

from ..datafiles import (
    PipelineError,
    atomic_write,
    check_account,
    check_assets,
    check_manifest,
    check_weth_params,
    encode_canonical,
    encode_jsonl,
    read_canonical,
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

DEFAULT_PRICE_USD8 = 300000000000   # $3,000, matching the Appendix A fixture
DEFAULT_LT_BPS = 8300
DEFAULT_BONUS_BPS = 10500
MIN_LTV_BPS = 4000                  # §9.5: LTV between 40% ...
LTV_MARGIN_BPS = 100                # ... and ltBps - 1%
MAX_COLLATERAL_ETH = 100
MAX_COUNT = 9999                    # synth-0001 .. synth-9999

FILTER = "collateral=WETH only; debt=stablecoins; eMode=0; isolation=false"
ZERO_ADDRESS = "0x" + "0" * 40


def generate_synthetic_accounts(
    seed: int,
    count: int = 20,
    price_usd8: int = DEFAULT_PRICE_USD8,
    lt_bps: int = DEFAULT_LT_BPS,
) -> List[dict]:
    """
    Deterministic, integers only. Collateral in whole ETH; LTV drawn from [40%, ltBps - 1%];
    debt = collateralValue0 * ltv // BPS, so every account is healthy at the unshocked price.
    """
    if not 1 <= count <= MAX_COUNT:
        raise ValueError(f"count must be in [1, {MAX_COUNT}]")
    if price_usd8 <= 0:
        raise ValueError("price_usd8 must be positive")
    if not MIN_LTV_BPS + LTV_MARGIN_BPS <= lt_bps <= MAX_LT_BPS:
        raise ValueError(f"lt_bps must be in [{MIN_LTV_BPS + LTV_MARGIN_BPS}, {MAX_LT_BPS}]")

    rng = random.Random(seed)
    accounts = []
    for i in range(1, count + 1):
        collateral_wei = rng.randint(1, MAX_COLLATERAL_ETH) * 10**EXPECTED_DECIMALS
        ltv_bps = rng.randint(MIN_LTV_BPS, lt_bps - LTV_MARGIN_BPS)
        collateral_value0 = collateral_wei * price_usd8 // 10**EXPECTED_DECIMALS
        accounts.append({
            "collateralAmount": str(collateral_wei),
            "debtUsd8": str(collateral_value0 * ltv_bps // BPS),
            "id": f"synth-{i:04d}",
            "origin": "synthetic",
        })
    return accounts


def synthetic_draft_manifest(dataset_id: str, seed: int) -> Dict:
    """Draft manifest for a fully synthetic dataset. normalize fills counts, hashes and provenance."""
    return {
        "counts": {"real": 0, "synthetic": 0},
        "dataClass": "SYNTHETIC",
        "dataProviderAddress": ZERO_ADDRESS,
        "datasetId": dataset_id,
        "excludedCounts": {
            "eMode": 0, "noDebt": 0, "nonStableDebt": 0, "nonWethCollateral": 0, "other": 0, "wethNotCollateral": 0,
        },
        "extractedAt": "",
        "extractionScriptCommit": "",
        "filter": FILTER,
        "forkBlock": 0,
        "forkBlockHash": "0x" + "0" * 64,
        "forkBlockTimestamp": 0,
        "network": "synthetic",
        "oracleAddress": ZERO_ADDRESS,
        "poolAddress": ZERO_ADDRESS,
        "poolAddressesProvider": ZERO_ADDRESS,
        "rpcProvider": "none",
        "snapshotHash": "",
        "stablecoinAllowlist": [],
        "syntheticSeed": seed,
        "wethAddress": ZERO_ADDRESS,
    }


def _dataset_state(out: Path, dataset_id: str) -> str:
    """
    "real"      pinned real dataset: real_accounts.jsonl + valid assets.json + valid draft manifest
    "fresh"     no pipeline file exists yet (no accounts, assets, draft, snapshot or manifest)
    "synthetic" this script's own previous output (assets + SYNTHETIC draft, no real accounts)
    Anything else is incomplete or inconsistent and is rejected rather than overwritten.
    """
    has_real = (out / REAL_ACCOUNTS).exists()
    has_assets = (out / ASSETS).exists()
    has_draft = (out / DRAFT_MANIFEST).exists()
    has_final = (out / MANIFEST).exists() or (out / SNAPSHOT).exists()
    if not (has_real or has_assets or has_draft or has_final):
        return "fresh"
    if has_final and not (has_assets and has_draft):
        raise PipelineError(f"{out.name}: {MANIFEST}/{SNAPSHOT} exist but the pin or synth inputs are missing; "
                            "refusing to start a new synthetic dataset over a finalized one")
    if has_real and not (has_assets and has_draft):
        missing = [n for n, ok in ((ASSETS, has_assets), (DRAFT_MANIFEST, has_draft)) if not ok]
        raise PipelineError(f"{out.name}: {REAL_ACCOUNTS} exists but {', '.join(missing)} is missing; "
                            "re-run the pin step before adding synthetic accounts")
    if has_assets != has_draft:
        present = ASSETS if has_assets else DRAFT_MANIFEST
        raise PipelineError(f"{out.name}: incomplete dataset ({present} exists without its pair); "
                            "remove the directory or re-run the step that created it")
    check_assets(read_canonical(out / ASSETS), ASSETS)
    draft = check_manifest(read_canonical(out / DRAFT_MANIFEST), DRAFT_MANIFEST, final=False)
    if draft["datasetId"] != dataset_id:
        raise PipelineError(f"{DRAFT_MANIFEST}: datasetId {draft['datasetId']!r} != {dataset_id!r}")
    if has_real:
        return "real"
    if draft["dataClass"] != "SYNTHETIC" or draft["network"] != "synthetic":
        raise PipelineError(f"{out.name}: draft manifest describes a {draft['dataClass']} dataset but "
                            f"{REAL_ACCOUNTS} is missing; refusing to overwrite it with synthetic settings")
    if (out / MANIFEST).exists():
        final = check_manifest(read_canonical(out / MANIFEST), MANIFEST, final=True)
        if final["dataClass"] != "SYNTHETIC" or final["datasetId"] != dataset_id:
            raise PipelineError(f"{out.name}: {MANIFEST} describes a {final['dataClass']} dataset "
                                f"{final['datasetId']!r}; refusing to overwrite it with synthetic settings")
    return "synthetic"


def run(seed: int, count: int, dataset_id: Optional[str], price_usd8: Optional[int],
        lt_bps: Optional[int], bonus_bps: Optional[int]) -> str:
    _require_param(seed, "seed", 0, None)
    _require_param(count, "count", 1, MAX_COUNT)
    dataset_id = dataset_id or f"weth-stable-synth-{seed}-v1"
    out = dataset_dir(dataset_id)
    state = _dataset_state(out, dataset_id)

    writes = []   # (path, bytes), written only after everything has been generated and checked
    if state == "real":
        # Real data from the pin step: keep its asset configuration unchanged.
        if any(v is not None for v in (price_usd8, lt_bps, bonus_bps)):
            raise PipelineError("dataset has real data; asset parameters come from the pin step and cannot be overridden")
        weth = read_canonical(out / ASSETS)["WETH"]
        price_usd8, lt_bps = int(weth["priceUsd8"]), weth["ltBps"]
        draft = read_canonical(out / DRAFT_MANIFEST)
        draft["syntheticSeed"] = seed
        writes.append((out / DRAFT_MANIFEST, encode_canonical(draft, DRAFT_MANIFEST)))
    else:
        price_usd8 = DEFAULT_PRICE_USD8 if price_usd8 is None else price_usd8
        lt_bps = DEFAULT_LT_BPS if lt_bps is None else lt_bps
        bonus_bps = DEFAULT_BONUS_BPS if bonus_bps is None else bonus_bps
        check_weth_params(price_usd8, lt_bps, bonus_bps, "synthetic assets")
        assets = check_assets({"WETH": {
            "bonusBps": bonus_bps, "decimals": EXPECTED_DECIMALS, "ltBps": lt_bps, "priceUsd8": str(price_usd8),
        }})
        writes.append((out / ASSETS, encode_canonical(assets, ASSETS)))
        draft = check_manifest(synthetic_draft_manifest(dataset_id, seed), DRAFT_MANIFEST, final=False)
        writes.append((out / DRAFT_MANIFEST, encode_canonical(draft, DRAFT_MANIFEST)))

    if lt_bps < MIN_LTV_BPS + LTV_MARGIN_BPS:
        raise PipelineError(f"ltBps {lt_bps} leaves no room for synthetic LTVs in [{MIN_LTV_BPS}, ltBps - {LTV_MARGIN_BPS}]")
    try:
        accounts = generate_synthetic_accounts(seed, count, price_usd8, lt_bps)
    except ValueError as e:
        raise PipelineError(str(e)) from None
    for i, acc in enumerate(accounts, start=1):
        check_account(acc, ORIGIN_SYNTHETIC, f"generated account {i}")
    writes.append((out / SYNTHETIC_ACCOUNTS, encode_jsonl(accounts, SYNTHETIC_ACCOUNTS)))

    for path, data in writes:
        atomic_write(path, data)
    print(f"wrote {len(accounts)} synthetic accounts to {out / SYNTHETIC_ACCOUNTS} ({state} dataset)")
    print(f"datasetId {dataset_id}")
    return dataset_id


def _require_param(value, name: str, lo, hi) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < lo or (hi is not None and value > hi):
        bound = f"[{lo}, {hi}]" if hi is not None else f">= {lo}"
        raise PipelineError(f"{name} must be an integer {bound}, got {value!r}")


def main(argv=None) -> int:
    load_env()
    p = argparse.ArgumentParser(description="Generate deterministic synthetic borrower accounts (plan §9.5).")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--count", type=int, default=40)
    p.add_argument("--dataset", help="datasetId (default weth-stable-synth-<seed>-v1)")
    p.add_argument("--price-usd8", type=int, help=f"WETH price, USD*1e8 (default {DEFAULT_PRICE_USD8})")
    p.add_argument("--lt-bps", type=int, help=f"liquidation threshold (default {DEFAULT_LT_BPS})")
    p.add_argument("--bonus-bps", type=int, help=f"liquidation bonus (default {DEFAULT_BONUS_BPS})")
    args = p.parse_args(argv)
    try:
        run(args.seed, args.count, args.dataset, args.price_usd8, args.lt_bps, args.bonus_bps)
    except (PipelineError, ValueError) as e:
        print(f"synth: error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
