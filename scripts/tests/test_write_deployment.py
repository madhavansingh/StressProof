"""Tests for scripts/write_deployment.py.

The writer must replace deployments/<chainId>.json only after a complete, confirmed deployment,
and must leave an existing file untouched on every failure. A fake JSON-RPC node stands in for
the chain; no network is used.

Run: .venv/bin/python -m pytest scripts/tests -p no:cacheprovider
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "write_deployment.py"
_spec = importlib.util.spec_from_file_location("write_deployment", SCRIPT)
wd = importlib.util.module_from_spec(_spec)
sys.modules["write_deployment"] = wd  # dataclasses look the module up while it loads
_spec.loader.exec_module(wd)

# Anvil's default deployer (account #0) and the addresses of its first three CREATEs.
DEPLOYER = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
RESOLVER = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
REGISTRY = "0x5fbdb2315678afecb367f032d93f642f64180aa3"
VAULT = "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512"
MARKET = "0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0"
CORE_MARKET_ID = "0x2701f07d2eb0de529ccb283ac9cd1ebb8ed772916b7db0822335d9bcdabbc026"
MARKET_ID_STRING = "aave-v3-eth-weth-stable"
GIT_SHA = "0123456789abcdef0123456789abcdef01234567"
HASHES = ("0x" + "11" * 32, "0x" + "22" * 32, "0x" + "33" * 32)
NAMES = ("StressRegistry", "DemoVault", "MockLendingMarket")
ADDRESSES = (REGISTRY, VAULT, MARKET)
ORIGINAL = '{"original": true}\n'


def _uint(value: int) -> str:
    return "0x" + format(value, "064x")


def _addr_word(address: str) -> str:
    return "0x" + "0" * 24 + address[2:]


def _receipt(tx_hash: str, address: str, block: int) -> Dict[str, Any]:
    return {"transactionHash": tx_hash, "status": "0x1", "contractAddress": address,
            "blockNumber": hex(block), "from": DEPLOYER}


def broadcast_doc() -> Dict[str, Any]:
    """The shape forge 1.8 writes to broadcast/<script>/<chainId>/run-latest.json."""
    return {
        "chain": 31337,
        "transactions": [
            {"hash": h, "transactionType": "CREATE", "contractName": n, "contractAddress": wd.to_checksum_address(a)}
            for h, n, a in zip(HASHES, NAMES, ADDRESSES)
        ],
        "receipts": [_receipt(h, a, 1 + i) for i, (h, a) in enumerate(zip(HASHES, ADDRESSES))],
    }


class FakeNode:
    """A consistent chain for the three deployed contracts. Tests change fields to break it."""

    def __init__(self) -> None:
        self.chain_id = 31337
        self.receipts = {h: _receipt(h, a, 7 + i) for i, (h, a) in enumerate(zip(HASHES, ADDRESSES))}
        self.code = {a: "0x6080" for a in ADDRESSES}
        self.values = {
            (REGISTRY, "BOND()"): _uint(10**16),
            (REGISTRY, "CHALLENGE_WINDOW()"): _uint(120),
            (REGISTRY, "RESOLUTION_WINDOW()"): _uint(300),
            (REGISTRY, "TOLERANCE_BPS()"): _uint(0),
            (REGISTRY, "resolver()"): _addr_word(RESOLVER),
            (VAULT, "registry()"): _addr_word(REGISTRY),
            (VAULT, "owner()"): _addr_word(DEPLOYER),
            (VAULT, "MARKET_ID()"): CORE_MARKET_ID,
            (VAULT, "PAUSE_THRESHOLD()"): _uint(400_000_000_002),
            (VAULT, "LTV_THRESHOLD()"): _uint(100_000_000_000),
            (VAULT, "REDUCED_LTV_BPS()"): _uint(5000),
            (VAULT, "DEFAULT_MAX_LTV_BPS()"): _uint(8000),
            (MARKET, "vault()"): _addr_word(VAULT),
        }
        self.calls: List[str] = []

    def __call__(self, method: str, params: List[Any]) -> Any:
        self.calls.append(method)
        if method == "eth_chainId":
            return hex(self.chain_id)
        if method == "eth_getTransactionReceipt":
            return self.receipts.get(params[0])
        if method == "eth_getCode":
            return self.code.get(params[0], "0x")
        if method == "eth_call":
            call = params[0]
            for (address, signature), result in self.values.items():
                if call["to"] == address and call["data"] == wd._selector(signature):
                    return result
            return "0x"
        raise AssertionError(f"unexpected RPC {method}")


@pytest.fixture
def workspace(tmp_path: Path) -> Dict[str, Path]:
    broadcast = tmp_path / "run-latest.json"
    broadcast.write_text(json.dumps(broadcast_doc()))
    out_dir = tmp_path / "deployments"
    out_dir.mkdir()
    out = out_dir / "31337.json"
    out.write_text(ORIGINAL)
    return {"broadcast": broadcast, "out": out, "tmp": tmp_path}


def _argv(ws: Dict[str, Path], **overrides: str) -> List[str]:
    args = {
        "--broadcast-file": str(ws["broadcast"]),
        "--chain-id": "31337",
        "--market-id-string": MARKET_ID_STRING,
        "--git-commit": GIT_SHA,
        "--not-before": str(time.time() - 60),
        "--out": str(ws["out"]),
    }
    args.update(overrides)
    return [part for pair in args.items() for part in pair]


def _run(ws: Dict[str, Path], node: FakeNode, **overrides: str) -> int:
    return wd.main(_argv(ws, **overrides), rpc_factory=lambda _url: node)


def _write_broadcast(ws: Dict[str, Path], doc: Dict[str, Any]) -> None:
    ws["broadcast"].write_text(json.dumps(doc))


def _assert_untouched(ws: Dict[str, Path]) -> None:
    assert ws["out"].read_text() == ORIGINAL
    leftovers = [p.name for p in ws["out"].parent.iterdir() if p.name != ws["out"].name]
    assert leftovers == [], f"temporary files left behind: {leftovers}"


# ------------------------------------------------------------------ success


def test_writes_documented_fields_from_chain(workspace):
    node = FakeNode()
    assert _run(workspace, node) == 0
    data = json.loads(workspace["out"].read_text())
    assert list(data) == [
        "chainId", "registry", "vault", "market", "registryDeployBlock", "resolver", "marketId",
        "marketIdString", "bondWei", "challengeWindowSec", "resolutionWindowSec", "pauseThresholdUsd8",
        "ltvThresholdUsd8", "reducedLtvBps", "defaultMaxLtvBps", "gitCommit",
    ]
    assert data == {
        "chainId": 31337,
        "registry": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
        "vault": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
        "market": "0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0",
        "registryDeployBlock": 7,  # from the node's receipt, not the simulation
        "resolver": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "marketId": CORE_MARKET_ID,
        "marketIdString": MARKET_ID_STRING,
        "bondWei": "10000000000000000",
        "challengeWindowSec": 120,
        "resolutionWindowSec": 300,
        "pauseThresholdUsd8": "400000000002",
        "ltvThresholdUsd8": "100000000000",
        "reducedLtvBps": 5000,
        "defaultMaxLtvBps": 8000,
        "gitCommit": GIT_SHA,
    }
    assert [p.name for p in workspace["out"].parent.iterdir()] == ["31337.json"]


def test_market_id_comes_from_core_library():
    from stressproof_core.hashing import market_id

    assert market_id(MARKET_ID_STRING) == CORE_MARKET_ID


def test_checksum_matches_eip55_vector():
    assert wd.to_checksum_address("0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed") == (
        "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
    )


def test_output_contains_no_rpc_url_or_keys(workspace, monkeypatch, capsys):
    monkeypatch.setenv(wd.RPC_URL_ENV, "https://eth.example/v2/SECRET-API-KEY")
    assert wd.main(_argv(workspace), rpc_factory=lambda _url: FakeNode()) == 0
    printed = capsys.readouterr()
    for text in (printed.out, printed.err, workspace["out"].read_text()):
        assert "SECRET-API-KEY" not in text


# ------------------------------------------------- broadcast record failures


def _drop_receipt(doc):
    doc["receipts"].pop(1)


def _fail_receipt(doc):
    doc["receipts"][2]["status"] = "0x0"


def _reorder(doc):
    doc["transactions"].reverse()


def _missing_contract(doc):
    doc["transactions"].pop()


def _extra_call(doc):
    doc["transactions"].append({"hash": "0x" + "44" * 32, "transactionType": "CALL", "contractName": None})


def _wrong_chain_in_record(doc):
    doc["chain"] = 1


@pytest.mark.parametrize(
    "corrupt",
    [_drop_receipt, _fail_receipt, _reorder, _missing_contract, _extra_call, _wrong_chain_in_record],
    ids=["no-receipt", "failed-receipt", "wrong-order", "missing-contract", "unexpected-tx", "wrong-chain"],
)
def test_bad_broadcast_record_is_not_written(workspace, corrupt):
    doc = copy.deepcopy(broadcast_doc())
    corrupt(doc)
    _write_broadcast(workspace, doc)
    assert _run(workspace, FakeNode()) == 1
    _assert_untouched(workspace)


def test_missing_broadcast_record_is_not_written(workspace):
    workspace["broadcast"].unlink()  # e.g. a dry run, which writes no broadcast record
    assert _run(workspace, FakeNode()) == 1
    _assert_untouched(workspace)


def test_stale_broadcast_record_from_earlier_run_is_not_written(workspace):
    old = time.time() - 3600
    os.utime(workspace["broadcast"], (old, old))
    assert _run(workspace, FakeNode(), **{"--not-before": str(time.time() - 60)}) == 1
    _assert_untouched(workspace)


def test_malformed_broadcast_record_is_not_written(workspace):
    workspace["broadcast"].write_text("{not json")
    assert _run(workspace, FakeNode()) == 1
    _assert_untouched(workspace)


# ---------------------------------------------------------- node failures


def _node_without_receipt(node):
    node.receipts.pop(HASHES[1])


def _node_failed_receipt(node):
    node.receipts[HASHES[0]]["status"] = "0x0"


def _node_other_address(node):
    node.receipts[HASHES[2]]["contractAddress"] = "0x" + "ab" * 20


def _node_no_code(node):
    node.code.pop(VAULT)


def _node_other_chain(node):
    node.chain_id = 84532


def _node_two_senders(node):
    node.receipts[HASHES[1]]["from"] = RESOLVER


def _node_tolerance(node):
    node.values[(REGISTRY, "TOLERANCE_BPS()")] = _uint(1)


def _node_vault_wrong_registry(node):
    node.values[(VAULT, "registry()")] = _addr_word("0x" + "cd" * 20)


def _node_market_wrong_vault(node):
    node.values[(MARKET, "vault()")] = _addr_word("0x" + "cd" * 20)


def _node_wrong_owner(node):
    node.values[(VAULT, "owner()")] = _addr_word(RESOLVER)


def _node_resolver_is_deployer(node):
    node.values[(REGISTRY, "resolver()")] = _addr_word(DEPLOYER)


def _node_wrong_market_id(node):
    node.values[(VAULT, "MARKET_ID()")] = "0x40d51381e4b3e8a71bbbf288e285817d4567c9c0f99b2eb8c15682fa08d3c7c2"


def _node_call_fails(node):
    node.values.pop((VAULT, "PAUSE_THRESHOLD()"))


@pytest.mark.parametrize(
    "corrupt",
    [
        _node_without_receipt, _node_failed_receipt, _node_other_address, _node_no_code, _node_other_chain,
        _node_two_senders, _node_tolerance, _node_vault_wrong_registry, _node_market_wrong_vault,
        _node_wrong_owner, _node_resolver_is_deployer, _node_wrong_market_id, _node_call_fails,
    ],
    ids=[
        "no-receipt", "failed-receipt", "other-address", "no-code", "other-chain", "two-senders",
        "tolerance", "vault-registry", "market-vault", "owner", "resolver-is-deployer", "market-id",
        "call-fails",
    ],
)
def test_unconfirmed_deployment_is_not_written(workspace, corrupt):
    node = FakeNode()
    corrupt(node)
    assert _run(workspace, node) == 1
    _assert_untouched(workspace)


def test_rpc_error_is_not_written(workspace):
    def broken(method, params):
        raise wd.DeploymentError(f"RPC {method} failed: URLError")

    assert wd.main(_argv(workspace), rpc_factory=lambda _url: broken) == 1
    _assert_untouched(workspace)


# ------------------------------------------------------- argument failures


@pytest.mark.parametrize(
    "overrides",
    [{"--chain-id": "1"}, {"--git-commit": "502831a"}, {"--git-commit": "0123456789ABCDEF0123456789abcdef01234567"}],
    ids=["mainnet", "short-sha", "uppercase-sha"],
)
def test_bad_arguments_are_rejected_before_any_rpc(workspace, overrides):
    node = FakeNode()
    assert _run(workspace, node, **overrides) == 1
    assert node.calls == []
    _assert_untouched(workspace)


def test_non_http_rpc_url_is_rejected(workspace, monkeypatch):
    monkeypatch.setenv(wd.RPC_URL_ENV, "file:///etc/passwd")
    assert wd.main(_argv(workspace)) == 1
    _assert_untouched(workspace)


# ---------------------------------------------------------- atomic write


def test_failed_rename_keeps_original_and_cleans_up(workspace, monkeypatch):
    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(wd.os, "replace", failing_replace)
    with pytest.raises(OSError):
        _run(workspace, FakeNode())
    _assert_untouched(workspace)
