"""
Claim verdict: the single entry point used by the watcher, resolver and attester self-check.
Matches Section 11 ("Verdict order") of implementationplan.md, with C-18 for informational metrics.
"""

from typing import Any, Dict, List, Optional

from .canonical_json import parse_strict
from .constants import (
    INFO_METRICS,
    VERDICT_EVIDENCE_INVALID,
    VERDICT_MATCH,
    VERDICT_WRONG_RESULT,
)
from .hashing import keccak256_hex
from .models import Evaluation
from .replay import replay
from .validation import validate

_REQUIRED_ONCHAIN = ("evidenceHash", "marketId", "claimedResidualBadDebt")


class VerdictInvariantError(RuntimeError):
    """An internal verdict rule was broken; never a property of the input bytes."""


def wrong_result_counter(recomputed_residual: int, claimed: int) -> int:
    """
    The counter-value for a WRONG_RESULT challenge. StressRegistry.challenge reverts with
    CounterEqualsClaim when they are equal, so equality is a bug and fails loudly. An explicit
    check, not an assert: `python -O` strips asserts.
    """
    if recomputed_residual == claimed:
        raise VerdictInvariantError("WRONG_RESULT counter equals the on-chain claim")
    return recomputed_residual


def _check_onchain(onchain: Dict[str, Any]) -> None:
    if not isinstance(onchain, dict):
        raise TypeError("onchain must be a dict")
    missing = [k for k in _REQUIRED_ONCHAIN if k not in onchain]
    if missing:
        raise ValueError(f"onchain is missing {missing}")
    claimed = onchain["claimedResidualBadDebt"]
    if not isinstance(claimed, int) or isinstance(claimed, bool) or claimed < 0:
        raise ValueError("onchain.claimedResidualBadDebt must be a non-negative int")


def _claimed_in_file(raw_bytes: bytes) -> Optional[str]:
    try:
        value = parse_strict(raw_bytes)["results"]["residualBadDebtUsd8"]
    except Exception:
        return None
    return value if isinstance(value, str) else None


def evaluate(raw_bytes: bytes, onchain: Dict[str, Any]) -> Evaluation:
    """
    Decide a claim from the fetched case-file bytes and the on-chain claim.

    onchain = {
        "evidenceHash": "0x..." (bytes32 hex),
        "marketId": "0x..." (bytes32 hex),
        "claimedResidualBadDebt": int (USD * 1e8),
    }

    Order:
      1. Any of V-01..V-13 fails      -> EVIDENCE_INVALID, counter 0, no replay.
      2. V-14 fails or the replayed residual differs from the on-chain claim
                                      -> WRONG_RESULT, counter = replayed residual.
         Edge case: V-14 fails but the replay equals the on-chain claim. A WRONG_RESULT
         challenge would revert (CounterEqualsClaim), and the file contradicts the claim it
         backs, so this is EVIDENCE_INVALID.
      3. Otherwise                    -> MATCH.
    Raises only for a malformed `onchain` argument (a caller bug), never for hostile bytes.
    """
    _check_onchain(onchain)
    claimed = onchain["claimedResidualBadDebt"]

    is_bytes = isinstance(raw_bytes, (bytes, bytearray)) and len(raw_bytes) > 0
    hash_matches = bool(is_bytes and isinstance(onchain["evidenceHash"], str)
                        and keccak256_hex(bytes(raw_bytes)) == onchain["evidenceHash"].lower())

    violations = validate(raw_bytes, onchain)
    structural = [v for v in violations if v.code != "V-14"]
    claimed_in_file = _claimed_in_file(bytes(raw_bytes)) if is_bytes and hash_matches else None

    if structural:
        return Evaluation(
            verdict=VERDICT_EVIDENCE_INVALID,
            violations=violations,
            hash_matches=hash_matches,
            recomputed=None,
            counter_residual_usd8=0,
            info_mismatches=[],
            claimed_in_file_usd8=claimed_in_file,
        )

    case_file = parse_strict(bytes(raw_bytes))
    result = replay(case_file)
    file_results = case_file["results"]
    recomputed_results = result.to_results_dict()
    info_mismatches: List[str] = [k for k in INFO_METRICS if recomputed_results[k] != file_results[k]]

    v14_failed = len(violations) > 0
    recomputed_residual = result.residual_bad_debt_usd8

    if recomputed_residual != claimed:
        verdict, counter = VERDICT_WRONG_RESULT, wrong_result_counter(recomputed_residual, claimed)
    elif v14_failed:
        verdict, counter = VERDICT_EVIDENCE_INVALID, 0
    else:
        verdict, counter = VERDICT_MATCH, 0

    return Evaluation(
        verdict=verdict,
        violations=violations,
        hash_matches=hash_matches,
        recomputed=result,
        counter_residual_usd8=counter,
        info_mismatches=info_mismatches,
        claimed_in_file_usd8=claimed_in_file,
    )
