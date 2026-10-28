"""
Evidence validation rules V-01 through V-14.
Matches Section 11 of implementationplan.md.
"""

import json
import re
from typing import Any, Dict, List, Optional

from .canonical_json import canonical_bytes
from .constants import (
    ACCOUNT_ID_REAL_REGEX,
    ACCOUNT_ID_SYNTH_REGEX,
    DECIMAL_REGEX,
    EXPECTED_DECIMALS,
    MAX_BONUS_BPS,
    MAX_LT_BPS,
    MAX_SHOCK_BPS,
    MIN_BONUS_BPS,
    MIN_LT_BPS,
    MIN_SHOCK_BPS,
    MODEL_ID,
    SCHEMA_VERSION,
)
from .hashing import keccak256_hex
from .models import Violation


def validate(
    raw_bytes: bytes,
    onchain: Optional[Dict[str, Any]] = None,
) -> List[Violation]:
    """
    Validates evidence bytes against normative rules V-01 to V-14.
    Returns list of violations. If any violation is returned, evidence is invalid.
    """
    violations: List[Violation] = []

    # V-01: Bytes presence
    if not raw_bytes or len(raw_bytes) == 0:
        return [Violation("V-01", "Payload is empty")]

    # V-02: Hash match
    if onchain and "evidenceHash" in onchain:
        computed_hash = keccak256_hex(raw_bytes)
        if computed_hash.lower() != onchain["evidenceHash"].lower():
            return [Violation("V-02", f"Hash mismatch: computed {computed_hash} != {onchain['evidenceHash']}")]

    # V-03: Canonical formatting
    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
        canonical = canonical_bytes(parsed)
        if canonical != raw_bytes:
            violations.append(Violation("V-03", "JSON bytes are not canonically formatted"))
            return violations
    except Exception as e:
        return [Violation("V-03", f"Malformed JSON: {str(e)}")]

    # V-04: Schema version & required top-level keys
    required_keys = {
        "agentRationale",
        "dataClass",
        "dataset",
        "marketId",
        "model",
        "results",
        "scenario",
        "schemaVersion",
        "snapshot",
    }
    if set(parsed.keys()) != required_keys:
        return [Violation("V-04", f"Keys mismatch. Expected {sorted(list(required_keys))}, got {sorted(list(parsed.keys()))}")]

    if parsed.get("schemaVersion") != SCHEMA_VERSION:
        violations.append(Violation("V-04", f"Unsupported schemaVersion {parsed.get('schemaVersion')}"))

    # V-05: marketId matches on-chain
    if onchain and "marketId" in onchain:
        market_id_hash = keccak256_hex(parsed["marketId"].encode("utf-8"))
        if market_id_hash.lower() != onchain["marketId"].lower():
            violations.append(Violation("V-05", f"marketId hash mismatch: {market_id_hash} != {onchain['marketId']}"))

    # V-06: Model ID
    if parsed["model"].get("id") != MODEL_ID:
        violations.append(Violation("V-06", f"Unknown model id {parsed['model'].get('id')}"))

    # V-07: Scenario asset exists in snapshot
    scenario_asset = parsed["scenario"].get("asset")
    if scenario_asset != "WETH" or scenario_asset not in parsed["snapshot"].get("assets", {}):
        violations.append(Violation("V-07", f"Invalid scenario asset {scenario_asset}"))

    # V-08: Domain constraints
    shock = parsed["scenario"].get("shockBps", 0)
    if not (MIN_SHOCK_BPS <= shock <= MAX_SHOCK_BPS):
        violations.append(Violation("V-08", f"shockBps {shock} outside [{MIN_SHOCK_BPS}, {MAX_SHOCK_BPS}]"))

    asset_data = parsed["snapshot"].get("assets", {}).get(scenario_asset, {})
    if asset_data.get("decimals") != EXPECTED_DECIMALS:
        violations.append(Violation("V-08", f"Expected {EXPECTED_DECIMALS} decimals, got {asset_data.get('decimals')}"))
    lt = asset_data.get("ltBps", 0)
    if not (MIN_LT_BPS <= lt <= MAX_LT_BPS):
        violations.append(Violation("V-08", f"ltBps {lt} outside [{MIN_LT_BPS}, {MAX_LT_BPS}]"))
    bonus = asset_data.get("bonusBps", 0)
    if not (MIN_BONUS_BPS <= bonus <= MAX_BONUS_BPS):
        violations.append(Violation("V-08", f"bonusBps {bonus} outside [{MIN_BONUS_BPS}, {MAX_BONUS_BPS}]"))

    # V-09: Amount formats
    dec_pattern = re.compile(DECIMAL_REGEX)
    if not dec_pattern.match(asset_data.get("priceUsd8", "")) or int(asset_data.get("priceUsd8", "0")) <= 0:
        violations.append(Violation("V-09", f"Invalid priceUsd8 {asset_data.get('priceUsd8')}"))

    for acc in parsed["snapshot"].get("accounts", []):
        if not dec_pattern.match(acc.get("collateralAmount", "")) or int(acc.get("collateralAmount", "0")) <= 0:
            violations.append(Violation("V-09", f"Invalid collateralAmount for {acc.get('id')}"))
        if not dec_pattern.match(acc.get("debtUsd8", "")):
            violations.append(Violation("V-09", f"Invalid debtUsd8 for {acc.get('id')}"))

    # V-10: Account IDs unique, ascending, and formatted
    accounts = parsed["snapshot"].get("accounts", [])
    account_ids = [acc.get("id", "") for acc in accounts]
    real_pat = re.compile(ACCOUNT_ID_REAL_REGEX)
    synth_pat = re.compile(ACCOUNT_ID_SYNTH_REGEX)

    seen = set()
    prev_id = ""
    for acc in accounts:
        acc_id = acc.get("id", "")
        if acc_id in seen:
            violations.append(Violation("V-10", f"Duplicate account ID: {acc_id}"))
        if prev_id and acc_id <= prev_id:
            violations.append(Violation("V-10", f"Accounts not strictly sorted: {acc_id} <= {prev_id}"))
        origin = acc.get("origin")
        if origin == "real_aave_v3_fork" and not real_pat.match(acc_id):
            violations.append(Violation("V-10", f"Malformed real address ID: {acc_id}"))
        elif origin == "synthetic" and not synth_pat.match(acc_id):
            violations.append(Violation("V-10", f"Malformed synthetic ID: {acc_id}"))
        seen.add(acc_id)
        prev_id = acc_id

    # V-11: Counts match snapshot
    counts = parsed["dataset"].get("counts", {})
    real_count = sum(1 for acc in accounts if acc.get("origin") == "real_aave_v3_fork")
    synth_count = sum(1 for acc in accounts if acc.get("origin") == "synthetic")
    if counts.get("real") != real_count or counts.get("synthetic") != synth_count:
        violations.append(Violation("V-11", f"Counts mismatch: manifest {counts} vs snapshot ({real_count}, {synth_count})"))

    # V-12: dataClass consistency
    data_class = parsed.get("dataClass")
    if synth_count == 0 and real_count > 0 and data_class != "REAL":
        violations.append(Violation("V-12", f"dataClass should be REAL, got {data_class}"))
    elif synth_count > 0 and real_count > 0 and data_class != "MIXED":
        violations.append(Violation("V-12", f"dataClass should be MIXED, got {data_class}"))
    elif real_count == 0 and synth_count > 0 and data_class != "SYNTHETIC":
        violations.append(Violation("V-12", f"dataClass should be SYNTHETIC, got {data_class}"))

    # V-13: Snapshot hash integrity
    snapshot_bytes = canonical_bytes(parsed["snapshot"])
    expected_snapshot_hash = parsed["dataset"].get("snapshotHash")
    computed_snapshot_hash = keccak256_hex(snapshot_bytes)
    if expected_snapshot_hash and computed_snapshot_hash.lower() != expected_snapshot_hash.lower():
        violations.append(Violation("V-13", f"snapshotHash mismatch: {computed_snapshot_hash} != {expected_snapshot_hash}"))

    # V-14: Claimed residual bad debt equals on-chain claimed
    if onchain and "claimedResidualBadDebt" in onchain:
        file_claimed = parsed["results"].get("residualBadDebtUsd8")
        onchain_claimed = str(onchain["claimedResidualBadDebt"])
        if file_claimed != onchain_claimed:
            violations.append(Violation("V-14", f"Claimed value mismatch: file {file_claimed} != onchain {onchain_claimed}"))

    return violations
