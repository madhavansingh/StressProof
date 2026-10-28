"""
Constants, bounds, and identifiers for stressproof_core.
"""

MODEL_ID: str = "static-liquidation-v1"
SCHEMA_VERSION: int = 1
DEFAULT_MARKET_ID_STRING: str = "aave-v3-eth-weth-stable"

BPS: int = 10_000

# Domain Bounds
MIN_SHOCK_BPS: int = -9000
MAX_SHOCK_BPS: int = -1

MIN_LT_BPS: int = 1
MAX_LT_BPS: int = 9999

MIN_BONUS_BPS: int = 10_001
MAX_BONUS_BPS: int = 15_000

EXPECTED_DECIMALS: int = 18

DECIMAL_REGEX: str = r"^(0|[1-9][0-9]*)$"
ACCOUNT_ID_REAL_REGEX: str = r"^0x[0-9a-f]{40}$"
ACCOUNT_ID_SYNTH_REGEX: str = r"^synth-\d{4}$"
