"""Shared fixtures: a valid deployment and a fake JSON-RPC node for web3.

The fake node implements just the methods the agents use. It keeps a nonce per sender, accepts
signed raw transactions (rejecting stale nonces like a real node), returns receipts with events,
and can be told to revert with any custom error. No network or real chain is involved.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest
from eth_abi import encode
from eth_account import Account
from eth_account.typed_transactions import TypedTransaction
from hexbytes import HexBytes
from web3 import Web3
from web3.providers.base import BaseProvider

REGISTRY = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
VAULT = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
MARKET = "0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0"
RESOLVER = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
CORE_MARKET_ID = "0x2701f07d2eb0de529ccb283ac9cd1ebb8ed772916b7db0822335d9bcdabbc026"
TEST_KEY = "0x" + "4c" * 32  # throwaway key for signing tests; never funded anywhere
TEST_ADDRESS = Account.from_key(TEST_KEY).address

DEPLOYMENT_JSON: Dict[str, Any] = {
    "chainId": 31337, "registry": REGISTRY, "vault": VAULT, "market": MARKET, "registryDeployBlock": 1,
    "resolver": RESOLVER, "marketId": CORE_MARKET_ID, "marketIdString": "aave-v3-eth-weth-stable",
    "bondWei": "10000000000000000", "challengeWindowSec": 120, "resolutionWindowSec": 300,
    "pauseThresholdUsd8": "400000000002", "ltvThresholdUsd8": "100000000000", "reducedLtvBps": 5000,
    "defaultMaxLtvBps": 8000, "gitCommit": "43ceec73e7e05372de2af9d9c360810e11f379b5",
}


def selector(signature: str) -> str:
    return "0x" + Web3.keccak(text=signature)[:4].hex()


def error_data(signature: str, types: List[str] = (), values: List[Any] = ()) -> str:
    return selector(signature) + encode(list(types), list(values)).hex()


class FakeNode(BaseProvider):
    """A minimal EIP-1559 chain as a web3 provider."""

    def __init__(self, chain_id: int = 31337) -> None:
        super().__init__()
        self.chain_id = chain_id
        self.code: Dict[str, str] = {a.lower(): "0x6080604052" for a in (REGISTRY, VAULT, MARKET)}
        self.calls: Dict[tuple, str] = {}
        self.nonces: Dict[str, int] = {}
        self.sent: List[dict] = []
        self.receipts: Dict[str, dict] = {}
        self.logs: List[dict] = []
        self.revert_next_estimate: Optional[str] = None  # revert data for the next eth_estimateGas
        self.revert_estimate_for: Dict[str, str] = {}  # function selector -> revert data, every time
        self.call_handlers: Dict[tuple, Callable[[str], str]] = {}  # (address, selector) -> f(calldata)
        self.on_send: List[Callable[[dict], None]] = []  # called with each accepted transaction
        self.log_queries: List[dict] = []
        self.fail_next_receipt = False
        self.requests: List[str] = []
        self.block_number = 10
        self._set_default_reads()

    # ---------------------------------------------------------------- setup

    def set_call(self, address: str, signature: str, types: List[str], values: List[Any]) -> None:
        self.calls[(address.lower(), selector(signature))] = "0x" + encode(types, values).hex()

    def _set_default_reads(self) -> None:
        self.set_call(REGISTRY, "BOND()", ["uint256"], [10**16])
        self.set_call(REGISTRY, "CHALLENGE_WINDOW()", ["uint64"], [120])
        self.set_call(REGISTRY, "RESOLUTION_WINDOW()", ["uint64"], [300])
        self.set_call(REGISTRY, "TOLERANCE_BPS()", ["uint16"], [0])
        self.set_call(REGISTRY, "resolver()", ["address"], [RESOLVER])
        self.set_call(REGISTRY, "claimCount()", ["uint256"], [0])
        self.set_call(VAULT, "registry()", ["address"], [REGISTRY])
        self.set_call(VAULT, "MARKET_ID()", ["bytes32"], [bytes.fromhex(CORE_MARKET_ID[2:])])
        self.set_call(MARKET, "vault()", ["address"], [VAULT])

    # ------------------------------------------------------------- provider

    def is_connected(self, show_traceback: bool = False) -> bool:
        return True

    def make_request(self, method, params):
        self.requests.append(method)
        handler: Optional[Callable] = getattr(self, "_" + method, None)
        if handler is None:
            return {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": f"fake node: no {method}"}}
        result = handler(params)
        if isinstance(result, dict) and result.get("__error__"):
            return {"jsonrpc": "2.0", "id": 1, "error": result["__error__"]}
        return {"jsonrpc": "2.0", "id": 1, "result": result}

    # -------------------------------------------------------------- methods

    def _eth_chainId(self, params):
        return hex(self.chain_id)

    def _eth_blockNumber(self, params):
        return hex(self.block_number)

    def _eth_getCode(self, params):
        return self.code.get(params[0].lower(), "0x")

    def _eth_call(self, params):
        call = params[0]
        handler = self.call_handlers.get((call["to"].lower(), call["data"][:10]))
        result = handler(call["data"]) if handler else self.calls.get((call["to"].lower(), call["data"][:10]))
        if result is None:
            return {"__error__": {"code": 3, "message": "execution reverted", "data": "0x"}}
        if result.startswith("revert:"):
            return {"__error__": {"code": 3, "message": "execution reverted", "data": result[len("revert:"):]}}
        return result

    def _eth_getTransactionCount(self, params):
        return hex(self.nonces.get(params[0].lower(), 0))

    def _eth_estimateGas(self, params):
        if self.revert_next_estimate is not None:
            data, self.revert_next_estimate = self.revert_next_estimate, None
            return {"__error__": {"code": 3, "message": "execution reverted", "data": data}}
        data = self.revert_estimate_for.get(str(params[0].get("data", ""))[:10])
        if data is not None:
            return {"__error__": {"code": 3, "message": "execution reverted", "data": data}}
        return hex(100_000)

    def _eth_maxPriorityFeePerGas(self, params):
        return hex(1_000_000_000)

    def _eth_getBlockByNumber(self, params):
        return {"number": hex(self.block_number), "timestamp": hex(1_700_000_000 + self.block_number),
                "baseFeePerGas": hex(7), "hash": "0x" + "ab" * 32, "parentHash": "0x" + "cd" * 32,
                "gasLimit": hex(30_000_000), "gasUsed": hex(0), "transactions": []}

    def _eth_sendRawTransaction(self, params):
        raw = HexBytes(params[0])
        tx = TypedTransaction.from_bytes(raw).as_dict()
        sender = Account.recover_transaction(raw).lower()
        expected = self.nonces.get(sender, 0)
        if tx["nonce"] < expected:
            return {"__error__": {"code": -32000, "message": "nonce too low"}}
        self.nonces[sender] = tx["nonce"] + 1
        tx_hash = "0x" + Web3.keccak(raw).hex()
        self.block_number += 1
        status = 0 if self.fail_next_receipt else 1
        self.fail_next_receipt = False
        self.sent.append({**tx, "from": sender, "hash": tx_hash})
        extra_logs = [log for hook in self.on_send for log in (hook({**tx, "from": sender}) or [])]
        self.receipts[tx_hash] = self._receipt(tx_hash, sender, tx, status, extra_logs)
        return tx_hash

    def _eth_getTransactionReceipt(self, params):
        return self.receipts.get(params[0])

    def _eth_getLogs(self, params):
        self.log_queries.append(params[0])
        low = int(params[0].get("fromBlock", "0x0"), 16)
        high = params[0].get("toBlock", "latest")
        high = self.block_number if high == "latest" else int(high, 16)
        return [copy.deepcopy(log) for log in self.logs if low <= int(log["blockNumber"], 16) <= high]

    def _receipt(self, tx_hash: str, sender: str, tx: dict, status: int, extra_logs=()) -> dict:
        logs = [dict(log, transactionHash=tx_hash, blockNumber=hex(self.block_number))
                for log in list(self.logs) + list(extra_logs)]
        return {
            "transactionHash": tx_hash, "transactionIndex": "0x0", "blockHash": "0x" + "ee" * 32,
            "blockNumber": hex(self.block_number), "from": sender, "to": "0x" + bytes(tx["to"]).hex(),
            "cumulativeGasUsed": hex(90_000), "gasUsed": hex(90_000), "effectiveGasPrice": hex(8),
            "contractAddress": None, "logs": logs, "logsBloom": "0x" + "00" * 256, "status": hex(status),
            "type": "0x2",
        }


def claim_posted_log(claim_id: int, attester: str, claimed: int, evidence_hash: str, uri: str,
                     deadline: int) -> dict:
    topic0 = "0x" + Web3.keccak(text="ClaimPosted(uint256,address,bytes32,uint256,bytes32,string,uint64)").hex()
    return {
        "address": REGISTRY,
        "topics": [topic0, "0x" + encode(["uint256"], [claim_id]).hex(),
                   "0x" + encode(["address"], [attester]).hex(), CORE_MARKET_ID],
        "data": "0x" + encode(["uint256", "bytes32", "string", "uint64"],
                              [claimed, bytes.fromhex(evidence_hash[2:]), uri, deadline]).hex(),
        "blockNumber": hex(5), "blockHash": "0x" + "ee" * 32, "transactionHash": "0x" + "77" * 32,
        "transactionIndex": "0x0", "logIndex": "0x0", "removed": False,
    }


@pytest.fixture
def deployment_json() -> Dict[str, Any]:
    return copy.deepcopy(DEPLOYMENT_JSON)


@pytest.fixture
def deployment_file(tmp_path: Path, deployment_json) -> Path:
    path = tmp_path / "31337.json"
    path.write_text(json.dumps(deployment_json))
    return path


@pytest.fixture
def node() -> FakeNode:
    return FakeNode()
