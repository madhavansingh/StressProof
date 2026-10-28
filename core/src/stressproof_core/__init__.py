"""
stressproof_core - Pure deterministic calculation engine and validation library.
"""

from .canonical_json import canonical_bytes, parse_strict
from .constants import BPS, MODEL_ID, SCHEMA_VERSION
from .hashing import keccak256_hex, market_id
from .models import (
    AccountOutcome,
    CaseFile,
    ReplayReport,
    ReplayResult,
    Snapshot,
    Violation,
)
from .replay import replay
from .validation import validate

__all__ = [
    "canonical_bytes",
    "parse_strict",
    "keccak256_hex",
    "market_id",
    "replay",
    "validate",
    "BPS",
    "MODEL_ID",
    "SCHEMA_VERSION",
    "AccountOutcome",
    "CaseFile",
    "ReplayReport",
    "ReplayResult",
    "Snapshot",
    "Violation",
]
