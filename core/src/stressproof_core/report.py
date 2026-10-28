"""
Builders for the two content-addressed documents: the case file (attester) and the
replay report (watcher). Matches implementationplan.md §8.3, §8.4 and docs/schemas/.
"""

import copy
from typing import Any, Dict, List, Mapping

from .canonical_json import canonical_bytes
from .constants import (
    DEFAULT_MARKET_ID_STRING,
    MAX_RATIONALE_CHARS,
    MODEL_ID,
    SCHEMA_VERSION,
)
from .models import CaseFile, Evaluation, ReplayReport
from .replay import replay

REPLAY_REPORT_KEYS = frozenset(ReplayReport.__annotations__)


def sanitize_rationale(text: str) -> str:
    """Strip control characters other than '\\n' and cap at MAX_RATIONALE_CHARS (§7.1 rule 7)."""
    if not isinstance(text, str):
        raise TypeError(f"rationale must be str, got {type(text)}")
    cleaned = "".join(ch for ch in text if ch == "\n" or (ord(ch) >= 32 and ord(ch) != 127))
    return cleaned[:MAX_RATIONALE_CHARS]


def build_case_file(
    snapshot: Mapping[str, Any],
    manifest: Mapping[str, Any],
    scenario: Mapping[str, Any],
    rationale: str,
    replayer_commit: str,
    market_id_string: str = DEFAULT_MARKET_ID_STRING,
) -> CaseFile:
    """
    Assemble a case file and fill `results` from replay(). Inputs are deep-copied.
    The caller serializes it with canonical_bytes() and should self-check it with validate().
    """
    case_file: Dict[str, Any] = {
        "agentRationale": sanitize_rationale(rationale),
        "dataClass": manifest["dataClass"],
        "dataset": copy.deepcopy(dict(manifest)),
        "marketId": market_id_string,
        "model": {"id": MODEL_ID, "replayerCommit": replayer_commit},
        "results": {},
        "scenario": {"asset": scenario["asset"], "shockBps": scenario["shockBps"]},
        "schemaVersion": SCHEMA_VERSION,
        "snapshot": copy.deepcopy(dict(snapshot)),
    }
    case_file["results"] = replay(case_file).to_results_dict()
    canonical_bytes(case_file)  # fail fast on non-canonical inputs
    return case_file  # type: ignore[return-value]


def build_replay_report(
    evaluation: Evaluation,
    *,
    chain_id: int,
    registry: str,
    claim_id: int,
    evidence_hash: str,
    fetched_from: str,
    watcher: str,
    replayer_commit: str,
    claimed_onchain_usd8: int,
    case_file_copy_uri: str = "",
) -> ReplayReport:
    """
    Build the watcher's replay report (docs/schemas/replay-report.md).
    `recomputed` and `claimedInFileUsd8` are null when the replay did not run or the file was unreadable.
    `violations` lists distinct V-codes. The result always serializes with canonical_bytes().
    """
    for name, value in (("claim_id", claim_id), ("claimed_onchain_usd8", claimed_onchain_usd8), ("chain_id", chain_id)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a non-negative int")

    report: Dict[str, Any] = {
        "caseFileCopyURI": case_file_copy_uri,
        "chainId": chain_id,
        "claimId": str(claim_id),
        "claimedInFileUsd8": evaluation.claimed_in_file_usd8,
        "claimedOnChainUsd8": str(claimed_onchain_usd8),
        "evidenceHash": evidence_hash.lower(),
        "fetchedFrom": fetched_from,
        "hashMatches": evaluation.hash_matches,
        "infoMismatches": list(evaluation.info_mismatches),
        "modelId": MODEL_ID,
        "recomputed": evaluation.recomputed.to_results_dict() if evaluation.recomputed is not None else None,
        "registry": registry,
        "replayerCommit": replayer_commit,
        "schemaVersion": SCHEMA_VERSION,
        "verdict": evaluation.verdict,
        "violations": evaluation.violation_codes,
        "watcher": watcher,
    }
    canonical_bytes(report)
    return report  # type: ignore[return-value]


def check_replay_report(obj: Any) -> List[str]:
    """Shape check for a parsed replay report (used by the backend on upload). Empty list = OK."""
    if not isinstance(obj, dict):
        return ["report must be a JSON object"]
    errors: List[str] = []
    missing = sorted(REPLAY_REPORT_KEYS - set(obj))
    extra = sorted(set(obj) - REPLAY_REPORT_KEYS)
    if missing:
        errors.append(f"missing keys {missing}")
    if extra:
        errors.append(f"unknown keys {extra}")
    if obj.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("unsupported schemaVersion")
    if obj.get("verdict") not in ("MATCH", "WRONG_RESULT", "EVIDENCE_INVALID"):
        errors.append("invalid verdict")
    return errors
