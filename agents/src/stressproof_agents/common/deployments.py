"""Load and verify deployments/<chainId>.json (implementationplan.md §8.7).

`load_deployment` checks the file on its own: exact fields, types, addresses, the chain, and that
marketId equals stressproof_core.market_id(marketIdString). `verify_on_chain` then checks the
connected node: chain id, code at every address, and that the on-chain constants (BOND, windows,
resolver, MARKET_ID, wiring) match the file. Agents must run both before sending anything.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

from stressproof_core.hashing import market_id
from web3 import Web3

from .config import ALLOWED_CHAIN_IDS

FIELDS: Tuple[str, ...] = (
    "chainId", "registry", "vault", "market", "registryDeployBlock", "resolver", "marketId",
    "marketIdString", "bondWei", "challengeWindowSec", "resolutionWindowSec", "pauseThresholdUsd8",
    "ltvThresholdUsd8", "reducedLtvBps", "defaultMaxLtvBps", "gitCommit",
)
_ADDRESS_FIELDS = ("registry", "vault", "market", "resolver")
_DECIMAL_FIELDS = ("bondWei", "pauseThresholdUsd8", "ltvThresholdUsd8")
_INT_FIELDS = ("chainId", "registryDeployBlock", "challengeWindowSec", "resolutionWindowSec",
               "reducedLtvBps", "defaultMaxLtvBps")
_DECIMAL_RE = re.compile(r"^(0|[1-9][0-9]*)$")
_BYTES32_RE = re.compile(r"^0x[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ZERO_ADDRESS = "0x" + "0" * 40


class DeploymentError(ValueError):
    """The deployments file is invalid or does not match the chain."""


@dataclass(frozen=True)
class Deployment:
    chain_id: int
    registry: str  # checksummed
    vault: str
    market: str
    registry_deploy_block: int
    resolver: str
    market_id: str  # 0x-prefixed lowercase bytes32
    market_id_string: str
    bond_wei: int
    challenge_window_sec: int
    resolution_window_sec: int
    pause_threshold_usd8: int
    ltv_threshold_usd8: int
    reduced_ltv_bps: int
    default_max_ltv_bps: int
    git_commit: str


def load_deployment(path: Path) -> Deployment:
    if not path.is_file():
        raise DeploymentError(f"deployments file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise DeploymentError(f"{path} is not valid JSON: {exc}") from None
    return parse_deployment(data, source=str(path))


def parse_deployment(data: Any, source: str = "deployment") -> Deployment:
    if not isinstance(data, dict) or set(data) != set(FIELDS):
        keys = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise DeploymentError(f"{source}: expected exactly the fields {list(FIELDS)}, got {keys}")
    _check_types(data, source)
    if data["chainId"] not in ALLOWED_CHAIN_IDS:
        raise DeploymentError(f"{source}: chainId {data['chainId']} is not allowed (only {ALLOWED_CHAIN_IDS})")
    expected_market_id = market_id(data["marketIdString"])
    if data["marketId"] != expected_market_id:
        raise DeploymentError(
            f"{source}: marketId {data['marketId']} != stressproof_core.market_id("
            f"{data['marketIdString']!r}) = {expected_market_id}"
        )
    return Deployment(
        chain_id=data["chainId"],
        registry=Web3.to_checksum_address(data["registry"]),
        vault=Web3.to_checksum_address(data["vault"]),
        market=Web3.to_checksum_address(data["market"]),
        registry_deploy_block=data["registryDeployBlock"],
        resolver=Web3.to_checksum_address(data["resolver"]),
        market_id=data["marketId"],
        market_id_string=data["marketIdString"],
        bond_wei=int(data["bondWei"]),
        challenge_window_sec=data["challengeWindowSec"],
        resolution_window_sec=data["resolutionWindowSec"],
        pause_threshold_usd8=int(data["pauseThresholdUsd8"]),
        ltv_threshold_usd8=int(data["ltvThresholdUsd8"]),
        reduced_ltv_bps=data["reducedLtvBps"],
        default_max_ltv_bps=data["defaultMaxLtvBps"],
        git_commit=data["gitCommit"],
    )


def _check_types(data: Dict[str, Any], source: str) -> None:
    for name in _ADDRESS_FIELDS:
        value = data[name]
        if not isinstance(value, str) or not Web3.is_address(value):
            raise DeploymentError(f"{source}: {name} is not an address: {value!r}")
        if value.lower() == _ZERO_ADDRESS:
            raise DeploymentError(f"{source}: {name} is the zero address (placeholder file; deploy first)")
        if value != value.lower() and not Web3.is_checksum_address(value):
            raise DeploymentError(f"{source}: {name} has an invalid EIP-55 checksum: {value}")
    for name in _DECIMAL_FIELDS:
        if not isinstance(data[name], str) or not _DECIMAL_RE.match(data[name]):
            raise DeploymentError(f"{source}: {name} must be a decimal string, got {data[name]!r}")
    for name in _INT_FIELDS:
        value = data[name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise DeploymentError(f"{source}: {name} must be a non-negative integer, got {value!r}")
    if not isinstance(data["marketId"], str) or not _BYTES32_RE.match(data["marketId"]):
        raise DeploymentError(f"{source}: marketId must be 0x + 64 lowercase hex characters")
    if not isinstance(data["marketIdString"], str) or not data["marketIdString"]:
        raise DeploymentError(f"{source}: marketIdString must be a non-empty string")
    if not isinstance(data["gitCommit"], str) or not _GIT_SHA_RE.match(data["gitCommit"]):
        raise DeploymentError(f"{source}: gitCommit must be 40 lowercase hex characters")


def verify_on_chain(deployment: Deployment, w3: Web3, registry, vault, market) -> None:
    """Checks the connected node against the deployments file. Read-only calls only."""
    node_chain_id = w3.eth.chain_id
    if node_chain_id != deployment.chain_id:
        raise DeploymentError(f"connected to chain {node_chain_id}, deployments file is for {deployment.chain_id}")
    for name in ("registry", "vault", "market"):
        address = getattr(deployment, name)
        if len(w3.eth.get_code(address)) == 0:
            raise DeploymentError(f"no contract code at {name} {address} on chain {node_chain_id}")

    checks = [
        ("BOND", registry.functions.BOND().call(), deployment.bond_wei),
        ("CHALLENGE_WINDOW", registry.functions.CHALLENGE_WINDOW().call(), deployment.challenge_window_sec),
        ("RESOLUTION_WINDOW", registry.functions.RESOLUTION_WINDOW().call(), deployment.resolution_window_sec),
        ("TOLERANCE_BPS", registry.functions.TOLERANCE_BPS().call(), 0),
        ("resolver", registry.functions.resolver().call(), deployment.resolver),
        ("vault.registry", vault.functions.registry().call(), deployment.registry),
        ("vault.MARKET_ID", "0x" + bytes(vault.functions.MARKET_ID().call()).hex(), deployment.market_id),
        ("market.vault", market.functions.vault().call(), deployment.vault),
    ]
    for label, on_chain, expected in checks:
        if on_chain != expected:
            raise DeploymentError(f"on-chain {label} is {on_chain}, deployments file says {expected}")
