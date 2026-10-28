"""Load the contract ABIs exported by scripts/export_abis.sh into stressproof_agents/abi/.

The files are generated from the Foundry build and committed; never edit them by hand.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Tuple

CONTRACTS: Tuple[str, ...] = ("StressRegistry", "DemoVault", "MockLendingMarket", "IStressRegistry")


class AbiError(RuntimeError):
    """An exported ABI is missing or malformed. Run `make abis`."""


@lru_cache(maxsize=None)
def load_abi(name: str) -> Tuple[Dict[str, Any], ...]:
    """The ABI as an immutable tuple of entries (cached; callers must not mutate entries)."""
    if name not in CONTRACTS:
        raise AbiError(f"unknown contract {name!r} (expected one of {CONTRACTS})")
    resource = resources.files("stressproof_agents").joinpath("abi", f"{name}.json")
    try:
        abi = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise AbiError(f"ABI for {name} not found; run `make abis`") from None
    except ValueError as exc:
        raise AbiError(f"ABI for {name} is not valid JSON: {exc}") from None
    if not isinstance(abi, list) or not all(isinstance(e, dict) and "type" in e for e in abi):
        raise AbiError(f"ABI for {name} is not a list of ABI entries")
    return tuple(abi)
