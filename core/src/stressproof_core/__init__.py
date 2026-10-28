"""
stressproof_core - Pure deterministic calculation engine and validation library.
"""

from .canonical_json import canonical_bytes, parse_strict
from .constants import BPS, MODEL_ID, SCHEMA_VERSION
from .hashing import keccak256_hex, market_id
from .models import (
    AccountOutcome,
    CaseFile,
    DatasetManifest,
    Evaluation,
    ReplayReport,
    ReplayResult,
    Snapshot,
    Violation,
)
from .replay import replay
from .report import (
    build_case_file,
    build_replay_report,
    check_replay_report,
    sanitize_rationale,
)
from .validation import validate
from .verdict import evaluate

__all__ = [
    "canonical_bytes",
    "parse_strict",
    "keccak256_hex",
    "market_id",
    "replay",
    "validate",
    "evaluate",
    "build_case_file",
    "build_replay_report",
    "check_replay_report",
    "sanitize_rationale",
    "BPS",
    "MODEL_ID",
    "SCHEMA_VERSION",
    "AccountOutcome",
    "CaseFile",
    "DatasetManifest",
    "Evaluation",
    "ReplayReport",
    "ReplayResult",
    "Snapshot",
    "Violation",
]
