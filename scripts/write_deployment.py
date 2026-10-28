"""Write deployments/<chainId>.json from a confirmed forge broadcast.

Called by scripts/deploy.sh after `forge script --broadcast` exits successfully. The file is
replaced only when every check passes:

1. Forge's broadcast record exists, was written by this run (not left over from an earlier one),
   and holds exactly the StressRegistry, DemoVault and MockLendingMarket CREATE transactions,
   in that order, each with a successful receipt.
2. The node itself returns a successful receipt for each transaction, at the recorded address,
   and there is code at each address.
3. Values read back from the deployed contracts are consistent: the vault points at the registry,
   the market at the vault, the vault owner is the deployer, TOLERANCE_BPS is 0, and the vault's
   MARKET_ID equals stressproof_core.market_id(MARKET_ID_STRING).

Every value in the output (implementationplan.md §8.7) comes from the chain or from the receipts,
except marketIdString and gitCommit. The write is atomic: a temporary file in the same folder is
renamed over the target, so a failure never leaves a partial file.

The RPC URL is read from the DEPLOY_RPC_URL environment variable and never printed, because
provider URLs often contain API keys. No private keys are read.

Usage (from the repo root, inside the uv environment):
    DEPLOY_RPC_URL=http://127.0.0.1:8546 uv run --no-sync python scripts/write_deployment.py \\
        --broadcast-file contracts/broadcast/Deploy.s.sol/31337/run-latest.json \\
        --chain-id 31337 --market-id-string aave-v3-eth-weth-stable \\
        --git-commit "$(git rev-parse HEAD)" --not-before 1700000000 --out deployments/31337.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from eth_hash.auto import keccak
from stressproof_core.hashing import market_id

EXPECTED_CONTRACTS: Tuple[str, ...] = ("StressRegistry", "DemoVault", "MockLendingMarket")
ALLOWED_CHAIN_IDS: Tuple[int, ...] = (31337, 84532)
RECEIPT_SUCCESS = "0x1"
RPC_TIMEOUT_SEC = 10
RPC_URL_ENV = "DEPLOY_RPC_URL"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
WORD_HEX_LEN = 2 + 64  # "0x" + 32 bytes

Rpc = Callable[[str, List[Any]], Any]


class DeploymentError(Exception):
    """A check failed. The deployments file is not written."""


@dataclass(frozen=True)
class DeployedContract:
    name: str
    address: str  # lowercase
    tx_hash: str  # lowercase


@dataclass(frozen=True)
class BroadcastRecord:
    chain_id: int
    contracts: Tuple[DeployedContract, ...]

    def address_of(self, name: str) -> str:
        return next(c.address for c in self.contracts if c.name == name)


# ----------------------------------------------------------------- encoding


def to_checksum_address(address: str) -> str:
    """EIP-55 mixed-case checksum, matching what forge and viem print."""
    if not ADDRESS_RE.match(address):
        raise DeploymentError(f"not an address: {address!r}")
    lower = address[2:].lower()
    digest = keccak(lower.encode("ascii")).hex()
    return "0x" + "".join(c.upper() if int(digest[i], 16) >= 8 else c for i, c in enumerate(lower))


def _lower_address(value: Any, what: str) -> str:
    if not isinstance(value, str) or not ADDRESS_RE.match(value):
        raise DeploymentError(f"{what} is not an address: {value!r}")
    return value.lower()


def _hex_int(value: Any, what: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise DeploymentError(f"{what} is not a hex quantity: {value!r}")
    return int(value, 16)


def _selector(signature: str) -> str:
    return "0x" + keccak(signature.encode("ascii"))[:4].hex()


# ---------------------------------------------------------------------- rpc


def http_rpc(url: str) -> Rpc:
    """Minimal JSON-RPC client. Errors never include the URL."""
    if not url.startswith(("http://", "https://")):
        raise DeploymentError(f"{RPC_URL_ENV} must be an http(s) URL")

    def call(method: str, params: List[Any]) -> Any:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=RPC_TIMEOUT_SEC) as response:
                reply = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise DeploymentError(f"RPC {method} failed: {type(exc).__name__}") from None
        if reply.get("error"):
            raise DeploymentError(f"RPC {method} returned an error: {reply['error']}")
        return reply.get("result")

    return call


def _eth_call_word(rpc: Rpc, address: str, signature: str) -> str:
    result = rpc("eth_call", [{"to": address, "data": _selector(signature)}, "latest"])
    if not isinstance(result, str) or len(result) != WORD_HEX_LEN:
        raise DeploymentError(f"{signature} on {address} returned {result!r}")
    return result


def _read_uint(rpc: Rpc, address: str, signature: str) -> int:
    return int(_eth_call_word(rpc, address, signature), 16)


def _read_address(rpc: Rpc, address: str, signature: str) -> str:
    return "0x" + _eth_call_word(rpc, address, signature)[-40:].lower()


def _read_bytes32(rpc: Rpc, address: str, signature: str) -> str:
    return _eth_call_word(rpc, address, signature).lower()


# ---------------------------------------------------------------- broadcast


def load_broadcast(path: Path, not_before: float) -> BroadcastRecord:
    """Reads forge's broadcast record and checks it describes a complete, successful run."""
    if not path.is_file():
        raise DeploymentError(f"broadcast record not found: {path}")
    if path.stat().st_mtime < not_before:
        raise DeploymentError(f"broadcast record {path} is older than this deploy run")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise DeploymentError(f"broadcast record is not valid JSON: {exc}") from None

    transactions = data.get("transactions") or []
    names = tuple(tx.get("contractName") for tx in transactions)
    kinds = {tx.get("transactionType") for tx in transactions}
    if names != EXPECTED_CONTRACTS or kinds != {"CREATE"}:
        raise DeploymentError(f"expected CREATE of {EXPECTED_CONTRACTS} in order, got {names}")

    receipts = {str(r.get("transactionHash", "")).lower(): r for r in data.get("receipts") or []}
    contracts = tuple(_contract_from(tx, receipts) for tx in transactions)
    chain_id = data.get("chain")
    if not isinstance(chain_id, int):
        raise DeploymentError(f"broadcast record has no chain id: {chain_id!r}")
    return BroadcastRecord(chain_id=chain_id, contracts=contracts)


def _contract_from(tx: Dict[str, Any], receipts: Dict[str, Dict[str, Any]]) -> DeployedContract:
    name = tx["contractName"]
    tx_hash = str(tx.get("hash", "")).lower()
    receipt = receipts.get(tx_hash)
    if receipt is None:
        raise DeploymentError(f"{name}: no receipt in the broadcast record")
    if receipt.get("status") != RECEIPT_SUCCESS:
        raise DeploymentError(f"{name}: transaction {tx_hash} failed (status {receipt.get('status')})")
    address = _lower_address(tx.get("contractAddress"), f"{name} contractAddress")
    return DeployedContract(name=name, address=address, tx_hash=tx_hash)


# ----------------------------------------------------------------- on-chain


def _confirmed_receipt(rpc: Rpc, contract: DeployedContract) -> Dict[str, Any]:
    receipt = rpc("eth_getTransactionReceipt", [contract.tx_hash])
    if not receipt:
        raise DeploymentError(f"{contract.name}: node has no receipt for {contract.tx_hash}")
    if receipt.get("status") != RECEIPT_SUCCESS:
        raise DeploymentError(f"{contract.name}: node reports transaction {contract.tx_hash} failed")
    created = _lower_address(receipt.get("contractAddress"), f"{contract.name} receipt contractAddress")
    if created != contract.address:
        raise DeploymentError(f"{contract.name}: receipt address {created} != recorded {contract.address}")
    code = rpc("eth_getCode", [contract.address, "latest"])
    if not isinstance(code, str) or code in ("0x", "0x0"):
        raise DeploymentError(f"{contract.name}: no code at {contract.address}")
    return receipt


def verify_on_chain(rpc: Rpc, record: BroadcastRecord, expected_chain_id: int, market_id_string: str) -> Dict[str, Any]:
    """Confirms the deployment with the node and returns the values read from the contracts."""
    node_chain_id = _hex_int(rpc("eth_chainId", []), "eth_chainId")
    if not (node_chain_id == record.chain_id == expected_chain_id):
        raise DeploymentError(
            f"chain mismatch: node {node_chain_id}, broadcast {record.chain_id}, expected {expected_chain_id}"
        )
    receipts = {c.name: _confirmed_receipt(rpc, c) for c in record.contracts}
    senders = {_lower_address(r.get("from"), "receipt from") for r in receipts.values()}
    if len(senders) != 1:
        raise DeploymentError(f"contracts were deployed by different senders: {sorted(senders)}")

    values = _read_contract_values(rpc, record)
    _check_wiring(values, record, deployer=senders.pop(), market_id_string=market_id_string)
    values["registryDeployBlock"] = _hex_int(receipts["StressRegistry"].get("blockNumber"), "blockNumber")
    return values


def _read_contract_values(rpc: Rpc, record: BroadcastRecord) -> Dict[str, Any]:
    registry = record.address_of("StressRegistry")
    vault = record.address_of("DemoVault")
    market = record.address_of("MockLendingMarket")
    return {
        "bondWei": _read_uint(rpc, registry, "BOND()"),
        "challengeWindowSec": _read_uint(rpc, registry, "CHALLENGE_WINDOW()"),
        "resolutionWindowSec": _read_uint(rpc, registry, "RESOLUTION_WINDOW()"),
        "toleranceBps": _read_uint(rpc, registry, "TOLERANCE_BPS()"),
        "resolver": _read_address(rpc, registry, "resolver()"),
        "vaultRegistry": _read_address(rpc, vault, "registry()"),
        "vaultOwner": _read_address(rpc, vault, "owner()"),
        "marketId": _read_bytes32(rpc, vault, "MARKET_ID()"),
        "pauseThresholdUsd8": _read_uint(rpc, vault, "PAUSE_THRESHOLD()"),
        "ltvThresholdUsd8": _read_uint(rpc, vault, "LTV_THRESHOLD()"),
        "reducedLtvBps": _read_uint(rpc, vault, "REDUCED_LTV_BPS()"),
        "defaultMaxLtvBps": _read_uint(rpc, vault, "DEFAULT_MAX_LTV_BPS()"),
        "marketVault": _read_address(rpc, market, "vault()"),
    }


def _check_wiring(values: Dict[str, Any], record: BroadcastRecord, deployer: str, market_id_string: str) -> None:
    expected_market_id = market_id(market_id_string).lower()
    checks = [
        (values["toleranceBps"] == 0, f"TOLERANCE_BPS is {values['toleranceBps']}, expected 0"),
        (values["vaultRegistry"] == record.address_of("StressRegistry"), "vault.registry() is not the registry"),
        (values["marketVault"] == record.address_of("DemoVault"), "market.vault() is not the vault"),
        (values["vaultOwner"] == deployer, "vault owner is not the deployer"),
        (values["resolver"] != deployer, "resolver is the deployer"),
        (values["marketId"] == expected_market_id, f"vault MARKET_ID != market_id({market_id_string!r})"),
    ]
    for ok, message in checks:
        if not ok:
            raise DeploymentError(message)


# ------------------------------------------------------------------- output


def build_deployment(record: BroadcastRecord, values: Dict[str, Any], market_id_string: str, git_commit: str) -> Dict[str, Any]:
    """The 16 fields of implementationplan.md §8.7. Amounts are decimal strings."""
    return {
        "chainId": record.chain_id,
        "registry": to_checksum_address(record.address_of("StressRegistry")),
        "vault": to_checksum_address(record.address_of("DemoVault")),
        "market": to_checksum_address(record.address_of("MockLendingMarket")),
        "registryDeployBlock": values["registryDeployBlock"],
        "resolver": to_checksum_address(values["resolver"]),
        "marketId": values["marketId"],
        "marketIdString": market_id_string,
        "bondWei": str(values["bondWei"]),
        "challengeWindowSec": values["challengeWindowSec"],
        "resolutionWindowSec": values["resolutionWindowSec"],
        "pauseThresholdUsd8": str(values["pauseThresholdUsd8"]),
        "ltvThresholdUsd8": str(values["ltvThresholdUsd8"]),
        "reducedLtvBps": values["reducedLtvBps"],
        "defaultMaxLtvBps": values["defaultMaxLtvBps"],
        "gitCommit": git_commit,
    }


def write_atomic(path: Path, payload: Dict[str, Any]) -> None:
    """Writes to a temp file in the same folder, fsyncs, then renames over `path`."""
    text = json.dumps(payload, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


# --------------------------------------------------------------------- main


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--broadcast-file", required=True, type=Path)
    parser.add_argument("--chain-id", required=True, type=int)
    parser.add_argument("--market-id-string", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--not-before", required=True, type=float, help="unix time the deploy run started")
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args(argv)


def run(args: argparse.Namespace, rpc: Rpc) -> Dict[str, Any]:
    if args.chain_id not in ALLOWED_CHAIN_IDS:
        raise DeploymentError(f"chain {args.chain_id} is not allowed (only {ALLOWED_CHAIN_IDS})")
    if not GIT_SHA_RE.match(args.git_commit):
        raise DeploymentError(f"git commit must be 40 lowercase hex characters: {args.git_commit!r}")
    if not args.out.parent.is_dir():
        raise DeploymentError(f"output folder does not exist: {args.out.parent}")
    record = load_broadcast(args.broadcast_file, args.not_before)
    values = verify_on_chain(rpc, record, args.chain_id, args.market_id_string)
    payload = build_deployment(record, values, args.market_id_string, args.git_commit)
    write_atomic(args.out, payload)
    return payload


def main(argv: Optional[Sequence[str]] = None, rpc_factory: Callable[[str], Rpc] = http_rpc) -> int:
    args = _parse_args(argv)
    try:
        rpc = rpc_factory(os.environ.get(RPC_URL_ENV, ""))
        payload = run(args, rpc)
    except DeploymentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"{args.out} was NOT written", file=sys.stderr)
        return 1
    print(f"Wrote {args.out} (registry {payload['registry']}, block {payload['registryDeployBlock']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
