"""
Constants, bounds, and identifiers for stressproof_core.
"""

MODEL_ID: str = "static-liquidation-v1"
SCHEMA_VERSION: int = 1
DEFAULT_MARKET_ID_STRING: str = "aave-v3-eth-weth-stable"
SCENARIO_ASSET: str = "WETH"

BPS: int = 10_000

# Domain Bounds (implementationplan.md §10.3)
MIN_SHOCK_BPS: int = -9000
MAX_SHOCK_BPS: int = -1

MIN_LT_BPS: int = 1
MAX_LT_BPS: int = 9999

MIN_BONUS_BPS: int = 10_001
MAX_BONUS_BPS: int = 15_000

# Aave configuration rule: liquidationThreshold * liquidationBonus <= 100%
MAX_LT_BONUS_PRODUCT: int = BPS * BPS

EXPECTED_DECIMALS: int = 18

# JSON numbers must stay exactly representable in JavaScript (§7.1 rule 3)
MAX_SAFE_INT: int = 2**53

# Free-text rationale limit (§7.1 rule 7)
MAX_RATIONALE_CHARS: int = 4000

DECIMAL_REGEX: str = r"^(0|[1-9][0-9]*)$"
ACCOUNT_ID_REAL_REGEX: str = r"^0x[0-9a-f]{40}$"
ACCOUNT_ID_SYNTH_REGEX: str = r"^synth-\d{4}$"
HASH_REGEX: str = r"^0x[0-9a-f]{64}$"

ORIGIN_REAL: str = "real_aave_v3_fork"
ORIGIN_SYNTHETIC: str = "synthetic"

DATA_CLASSES: tuple = ("REAL", "MIXED", "SYNTHETIC")

VERDICT_MATCH: str = "MATCH"
VERDICT_WRONG_RESULT: str = "WRONG_RESULT"
VERDICT_EVIDENCE_INVALID: str = "EVIDENCE_INVALID"

# Informational metrics: compared and reported, never adjudicated (C-18)
INFO_METRICS: tuple = ("debtAtRiskUsd8", "liquidatableAccounts", "liquidationVolumeUsd8")
