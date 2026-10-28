"""The one dishonest behaviour the MVP demonstrates (implementationplan.md §15.4, spec §11).

Take an honest, valid case file and change only results.residualBadDebtUsd8 to 3x the honest
value. Snapshot, scenario, rationale and every other field stay byte-for-byte the same. The result
is re-serialized with the core library's canonical_bytes, so it is well formed and hash-consistent:
it passes V-01..V-14 against a claim of 3R, and only the replay shows it is wrong (WRONG_RESULT,
counter R). Omitted borrowers or a stale block are deliberately not scripted (spec §11).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict

from stressproof_core import canonical_bytes, keccak256_hex, parse_strict

INFLATION_FACTOR = 3


class TamperError(RuntimeError):
    """The honest input is unusable, or the tampered file is not what the demo needs."""


@dataclass(frozen=True)
class InflatedCaseFile:
    raw: bytes
    evidence_hash: str
    honest_hash: str
    honest_usd8: int
    inflated_usd8: int


def inflate_residual(honest_raw: bytes, factor: int = INFLATION_FACTOR) -> InflatedCaseFile:
    try:
        honest = parse_strict(honest_raw)  # also rejects non-canonical bytes
    except Exception as exc:
        raise TamperError(f"honest case file is not canonical JSON: {exc}") from None
    honest_value = _residual(honest)
    if honest_value <= 0:
        # 3 x 0 = 0 would post a "dishonest" claim equal to the honest one (plan §15.4 step 6).
        raise TamperError("honest residual bad debt is 0; choose a scenario with R > 0")

    tampered = copy.deepcopy(honest)
    tampered["results"]["residualBadDebtUsd8"] = str(factor * honest_value)
    raw = canonical_bytes(tampered)
    _require_only_residual_changed(honest, parse_strict(raw))
    return InflatedCaseFile(raw=raw, evidence_hash=keccak256_hex(raw), honest_hash=keccak256_hex(honest_raw),
                            honest_usd8=honest_value, inflated_usd8=factor * honest_value)


def _residual(case_file: Any) -> int:
    try:
        value = case_file["results"]["residualBadDebtUsd8"]
    except (TypeError, KeyError):
        raise TamperError("honest case file has no results.residualBadDebtUsd8") from None
    if not isinstance(value, str) or not value.isdigit():
        raise TamperError(f"honest residualBadDebtUsd8 is not a decimal string: {value!r}")
    return int(value)


def _require_only_residual_changed(honest: Dict[str, Any], tampered: Dict[str, Any]) -> None:
    restored = copy.deepcopy(tampered)
    restored["results"]["residualBadDebtUsd8"] = honest["results"]["residualBadDebtUsd8"]
    if canonical_bytes(restored) != canonical_bytes(honest):
        raise TamperError("tampering changed more than results.residualBadDebtUsd8")
