"""
Evidence validation rules V-01 through V-14.
Matches Section 11 of implementationplan.md.

validate() never raises on hostile input: every malformed byte string, wrong type or
missing key becomes a Violation. Rules stop at the first structural failure (V-01..V-04)
so that later rules can rely on the structure.
"""

import re
from typing import Any, Dict, List, Optional

from .canonical_json import canonical_bytes, parse_strict
from .constants import (
    ACCOUNT_ID_REAL_REGEX,
    ACCOUNT_ID_SYNTH_REGEX,
    DATA_CLASSES,
    DECIMAL_REGEX,
    EXPECTED_DECIMALS,
    MAX_BONUS_BPS,
    MAX_LT_BONUS_PRODUCT,
    MAX_LT_BPS,
    MAX_RATIONALE_CHARS,
    MAX_SHOCK_BPS,
    MIN_BONUS_BPS,
    MIN_LT_BPS,
    MIN_SHOCK_BPS,
    MODEL_ID,
    ORIGIN_REAL,
    ORIGIN_SYNTHETIC,
    SCENARIO_ASSET,
    SCHEMA_VERSION,
)
from .hashing import keccak256_hex
from .models import Violation

_DEC = re.compile(DECIMAL_REGEX)
_REAL_ID = re.compile(ACCOUNT_ID_REAL_REGEX)
_SYNTH_ID = re.compile(ACCOUNT_ID_SYNTH_REGEX)

# --- Strict schema (V-04) ----------------------------------------------------
# Type markers. AMOUNT accepts str or int here so that a JSON number in an amount
# field is reported as V-09 (wrong representation) rather than V-04 (T-P-38).
STR = "str"
INT = "int"
OPT_INT = "int|null"
AMOUNT = "amount"


class _MapOf:
    def __init__(self, value_spec: Any):
        self.value_spec = value_spec


_MANIFEST_SPEC = {
    "counts": {"real": INT, "synthetic": INT},
    "dataClass": STR,
    "datasetId": STR,
    "dataProviderAddress": STR,
    "excludedCounts": {
        "eMode": INT,
        "noDebt": INT,
        "nonStableDebt": INT,
        "nonWethCollateral": INT,
        "other": INT,
        "wethNotCollateral": INT,
    },
    "extractedAt": STR,
    "extractionScriptCommit": STR,
    "filter": STR,
    "forkBlock": INT,
    "forkBlockHash": STR,
    "forkBlockTimestamp": INT,
    "network": STR,
    "oracleAddress": STR,
    "poolAddress": STR,
    "poolAddressesProvider": STR,
    "rpcProvider": STR,
    "snapshotHash": STR,
    "stablecoinAllowlist": [{"address": STR, "symbol": STR}],
    "syntheticSeed": OPT_INT,
    "wethAddress": STR,
}

_ACCOUNT_SPEC = {"collateralAmount": AMOUNT, "debtUsd8": AMOUNT, "id": STR, "origin": STR}
_ASSET_SPEC = {"bonusBps": INT, "decimals": INT, "ltBps": INT, "priceUsd8": AMOUNT}
_RESULTS_SPEC = {
    "debtAtRiskUsd8": AMOUNT,
    "liquidatableAccounts": INT,
    "liquidationVolumeUsd8": AMOUNT,
    "residualBadDebtUsd8": AMOUNT,
}

CASE_FILE_SPEC = {
    "agentRationale": STR,
    "dataClass": STR,
    "dataset": _MANIFEST_SPEC,
    "marketId": STR,
    "model": {"id": STR, "replayerCommit": STR},
    "results": _RESULTS_SPEC,
    "scenario": {"asset": STR, "shockBps": INT},
    "schemaVersion": INT,
    "snapshot": {"accounts": [_ACCOUNT_SPEC], "assets": _MapOf(_ASSET_SPEC)},
}

_MAX_SCHEMA_ERRORS = 20


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _type_name(v: Any) -> str:
    return "null" if v is None else type(v).__name__


def _check_schema(value: Any, spec: Any, path: str, errors: List[str]) -> None:
    if len(errors) >= _MAX_SCHEMA_ERRORS:
        return
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object, got {_type_name(value)}")
            return
        missing = sorted(set(spec) - set(value))
        extra = sorted(set(value) - set(spec))
        if missing:
            errors.append(f"{path}: missing keys {missing}")
        if extra:
            errors.append(f"{path}: unknown keys {extra}")
        for key, sub in spec.items():
            if key in value:
                _check_schema(value[key], sub, f"{path}.{key}", errors)
    elif isinstance(spec, list):
        if not isinstance(value, list):
            errors.append(f"{path}: expected array, got {_type_name(value)}")
            return
        for i, item in enumerate(value):
            _check_schema(item, spec[0], f"{path}[{i}]", errors)
    elif isinstance(spec, _MapOf):
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object, got {_type_name(value)}")
            return
        for key, item in value.items():
            _check_schema(item, spec.value_spec, f"{path}.{key}", errors)
    elif spec == STR:
        if not isinstance(value, str):
            errors.append(f"{path}: expected string, got {_type_name(value)}")
    elif spec == INT:
        if not _is_int(value):
            errors.append(f"{path}: expected integer, got {_type_name(value)}")
    elif spec == OPT_INT:
        if value is not None and not _is_int(value):
            errors.append(f"{path}: expected integer or null, got {_type_name(value)}")
    elif spec == AMOUNT:
        if not (isinstance(value, str) or _is_int(value)):
            errors.append(f"{path}: expected decimal string, got {_type_name(value)}")
    else:  # pragma: no cover - programming error in the spec itself
        raise AssertionError(f"unknown schema spec {spec!r}")


def _rationale_ok(text: str) -> bool:
    if len(text) > MAX_RATIONALE_CHARS:
        return False
    return all(ch == "\n" or (ord(ch) >= 32 and ord(ch) != 127) for ch in text)


def _is_amount(v: Any, positive: bool = False) -> bool:
    if not isinstance(v, str) or not _DEC.match(v):
        return False
    return int(v) > 0 if positive else True


def _onchain_value(onchain: Optional[Dict[str, Any]], key: str) -> Any:
    if onchain is None:
        return None
    return onchain.get(key)


def validate(
    raw_bytes: bytes,
    onchain: Optional[Dict[str, Any]] = None,
) -> List[Violation]:
    """
    Validates evidence bytes against normative rules V-01 to V-14.

    onchain (optional) may contain:
      evidenceHash            0x-hex bytes32, enables V-02
      marketId                0x-hex bytes32, enables V-05
      claimedResidualBadDebt  int (USD * 1e8), enables V-14
    With onchain=None (backend self-check) V-02, V-05 and V-14 are skipped.

    Returns a list of violations; an empty list means the evidence is valid. V-14 alone
    means the file is well formed but disagrees with the on-chain claim (see verdict.evaluate).
    """
    # V-01: Bytes presence
    if not isinstance(raw_bytes, (bytes, bytearray)) or len(raw_bytes) == 0:
        return [Violation("V-01", "Payload is empty or not bytes")]
    raw_bytes = bytes(raw_bytes)

    # V-02: Hash match (never replay on failure)
    expected_hash = _onchain_value(onchain, "evidenceHash")
    if expected_hash is not None:
        computed_hash = keccak256_hex(raw_bytes)
        if not isinstance(expected_hash, str) or computed_hash != expected_hash.lower():
            return [Violation("V-02", f"Hash mismatch: computed {computed_hash} != {expected_hash}")]

    # V-03: Canonical JSON
    try:
        parsed = parse_strict(raw_bytes)
    except ValueError as e:
        return [Violation("V-03", str(e))]

    # V-04: Strict schema, exact key sets at every level, schemaVersion
    errors: List[str] = []
    _check_schema(parsed, CASE_FILE_SPEC, "$", errors)
    if errors:
        return [Violation("V-04", msg) for msg in errors]
    if parsed["schemaVersion"] != SCHEMA_VERSION:
        return [Violation("V-04", f"Unsupported schemaVersion {parsed['schemaVersion']}")]
    if not _rationale_ok(parsed["agentRationale"]):
        return [
            Violation(
                "V-04",
                f"agentRationale exceeds {MAX_RATIONALE_CHARS} chars or contains control characters",
            )
        ]

    violations: List[Violation] = []
    snapshot = parsed["snapshot"]
    dataset = parsed["dataset"]
    accounts = snapshot["accounts"]

    # V-05: marketId matches on-chain
    expected_market = _onchain_value(onchain, "marketId")
    if expected_market is not None:
        market_hash = keccak256_hex(parsed["marketId"].encode("utf-8"))
        if not isinstance(expected_market, str) or market_hash != expected_market.lower():
            violations.append(Violation("V-05", f"marketId hash mismatch: {market_hash} != {expected_market}"))

    # V-06: Model ID
    if parsed["model"]["id"] != MODEL_ID:
        violations.append(Violation("V-06", f"Unknown model id {parsed['model']['id']!r}"))

    # V-07: Scenario asset
    scenario_asset = parsed["scenario"]["asset"]
    asset = snapshot["assets"].get(scenario_asset) if scenario_asset == SCENARIO_ASSET else None
    if asset is None:
        violations.append(Violation("V-07", f"Invalid or missing scenario asset {scenario_asset!r}"))

    # V-08: Domain constraints
    shock = parsed["scenario"]["shockBps"]
    if not (MIN_SHOCK_BPS <= shock <= MAX_SHOCK_BPS):
        violations.append(Violation("V-08", f"shockBps {shock} outside [{MIN_SHOCK_BPS}, {MAX_SHOCK_BPS}]"))
    if asset is not None:
        if asset["decimals"] != EXPECTED_DECIMALS:
            violations.append(Violation("V-08", f"Expected {EXPECTED_DECIMALS} decimals, got {asset['decimals']}"))
        lt, bonus = asset["ltBps"], asset["bonusBps"]
        if not (MIN_LT_BPS <= lt <= MAX_LT_BPS):
            violations.append(Violation("V-08", f"ltBps {lt} outside [{MIN_LT_BPS}, {MAX_LT_BPS}]"))
        if not (MIN_BONUS_BPS <= bonus <= MAX_BONUS_BPS):
            violations.append(Violation("V-08", f"bonusBps {bonus} outside [{MIN_BONUS_BPS}, {MAX_BONUS_BPS}]"))
        if lt * bonus > MAX_LT_BONUS_PRODUCT:
            violations.append(Violation("V-08", f"ltBps * bonusBps = {lt * bonus} exceeds {MAX_LT_BONUS_PRODUCT}"))

    # V-09: Amount representation (decimal strings only)
    for name, a in snapshot["assets"].items():
        if not _is_amount(a["priceUsd8"], positive=True):
            violations.append(Violation("V-09", f"Invalid priceUsd8 for asset {name!r}"))
    for acc in accounts:
        if not _is_amount(acc["collateralAmount"], positive=True):
            violations.append(Violation("V-09", f"Invalid collateralAmount for {acc['id']!r}"))
        if not _is_amount(acc["debtUsd8"]):
            violations.append(Violation("V-09", f"Invalid debtUsd8 for {acc['id']!r}"))
    results = parsed["results"]
    for key in ("debtAtRiskUsd8", "liquidationVolumeUsd8", "residualBadDebtUsd8"):
        if not _is_amount(results[key]):
            violations.append(Violation("V-09", f"Invalid results.{key}"))
    if results["liquidatableAccounts"] < 0:
        violations.append(Violation("V-09", "results.liquidatableAccounts is negative"))

    # V-10: Account IDs unique, strictly ascending, well formed, origin matches id form
    seen = set()
    prev_id: Optional[str] = None
    for acc in accounts:
        acc_id, origin = acc["id"], acc["origin"]
        if acc_id in seen:
            violations.append(Violation("V-10", f"Duplicate account ID: {acc_id!r}"))
        elif prev_id is not None and acc_id <= prev_id:
            violations.append(Violation("V-10", f"Accounts not strictly ascending: {acc_id!r} after {prev_id!r}"))
        if origin == ORIGIN_REAL:
            if not _REAL_ID.match(acc_id):
                violations.append(Violation("V-10", f"Malformed real account ID: {acc_id!r}"))
        elif origin == ORIGIN_SYNTHETIC:
            if not _SYNTH_ID.match(acc_id):
                violations.append(Violation("V-10", f"Malformed synthetic account ID: {acc_id!r}"))
        else:
            violations.append(Violation("V-10", f"Unknown origin {origin!r} for {acc_id!r}"))
        seen.add(acc_id)
        prev_id = acc_id

    # V-11: Counts match snapshot
    real_count = sum(1 for acc in accounts if acc["origin"] == ORIGIN_REAL)
    synth_count = sum(1 for acc in accounts if acc["origin"] == ORIGIN_SYNTHETIC)
    counts = dataset["counts"]
    if counts["real"] != real_count or counts["synthetic"] != synth_count:
        violations.append(
            Violation("V-11", f"Counts mismatch: manifest {counts} vs snapshot real={real_count} synthetic={synth_count}")
        )

    # V-12: dataClass consistent with origins and with the manifest
    data_class = parsed["dataClass"]
    if data_class not in DATA_CLASSES:
        violations.append(Violation("V-12", f"Unknown dataClass {data_class!r}"))
    if real_count == 0 and synth_count == 0:
        violations.append(Violation("V-12", "Snapshot contains no accounts"))
    else:
        expected_class = "REAL" if synth_count == 0 else ("SYNTHETIC" if real_count == 0 else "MIXED")
        if data_class != expected_class:
            violations.append(Violation("V-12", f"dataClass should be {expected_class}, got {data_class!r}"))
    if dataset["dataClass"] != data_class:
        violations.append(Violation("V-12", f"dataset.dataClass {dataset['dataClass']!r} != dataClass {data_class!r}"))

    # V-13: Snapshot hash integrity
    computed_snapshot_hash = keccak256_hex(canonical_bytes(snapshot))
    if computed_snapshot_hash != dataset["snapshotHash"].lower():
        violations.append(
            Violation("V-13", f"snapshotHash mismatch: {computed_snapshot_hash} != {dataset['snapshotHash']}")
        )

    # V-14: Claimed value in the file equals the on-chain claim
    onchain_claimed = _onchain_value(onchain, "claimedResidualBadDebt")
    if onchain_claimed is not None:
        if not _is_int(onchain_claimed) or results["residualBadDebtUsd8"] != str(onchain_claimed):
            violations.append(
                Violation(
                    "V-14",
                    f"Claimed value mismatch: file {results['residualBadDebtUsd8']} != onchain {onchain_claimed}",
                )
            )

    return violations
