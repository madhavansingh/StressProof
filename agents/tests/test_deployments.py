"""Loading deployments/<chainId>.json and checking it against the chain."""

import json
from pathlib import Path

import pytest
from eth_abi import encode
from web3 import Web3

from stressproof_agents.common.abi import load_abi
from stressproof_agents.common.deployments import DeploymentError, load_deployment, verify_on_chain

from conftest import CORE_MARKET_ID, MARKET, REGISTRY, RESOLVER, VAULT, FakeNode

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(tmp_path, data):
    path = tmp_path / "d.json"
    path.write_text(json.dumps(data))
    return path


def test_committed_local_deployment_loads():
    d = load_deployment(REPO_ROOT / "deployments" / "31337.json")
    assert d.chain_id == 31337 and d.market_id == CORE_MARKET_ID and d.bond_wei == 10**16


def test_placeholder_testnet_file_is_rejected():
    with pytest.raises(DeploymentError, match="zero address"):
        load_deployment(REPO_ROOT / "deployments" / "84532.json")


def test_valid_file_is_parsed(deployment_file):
    d = load_deployment(deployment_file)
    assert d.registry == REGISTRY and d.resolver == RESOLVER and d.pause_threshold_usd8 == 400_000_000_002
    with pytest.raises(AttributeError):
        d.bond_wei = 1  # frozen


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d.pop("gitCommit"), "expected exactly the fields"),
    (lambda d: d.update(extra=1), "expected exactly the fields"),
    (lambda d: d.update(chainId=1), "chainId 1 is not allowed"),
    (lambda d: d.update(chainId="31337"), "chainId must be a non-negative integer"),
    (lambda d: d.update(registryDeployBlock=True), "registryDeployBlock must be a non-negative integer"),
    (lambda d: d.update(registry="0x123"), "registry is not an address"),
    (lambda d: d.update(vault="0x" + "0" * 40), "vault is the zero address"),
    (lambda d: d.update(market=MARKET.replace("f", "F", 1)), "invalid EIP-55 checksum"),
    (lambda d: d.update(bondWei=10**16), "bondWei must be a decimal string"),
    (lambda d: d.update(bondWei="01"), "bondWei must be a decimal string"),
    (lambda d: d.update(marketId=CORE_MARKET_ID.upper().replace("0X", "0x")), "marketId must be 0x"),
    (lambda d: d.update(marketId="0x40d51381e4b3e8a71bbbf288e285817d4567c9c0f99b2eb8c15682fa08d3c7c2"),
     "stressproof_core.market_id"),
    (lambda d: d.update(marketIdString="other-market"), "stressproof_core.market_id"),
    (lambda d: d.update(gitCommit="0000"), "gitCommit must be 40 lowercase hex"),
])
def test_malformed_deployment_is_rejected(tmp_path, deployment_json, mutate, message):
    mutate(deployment_json)
    with pytest.raises(DeploymentError, match=message):
        load_deployment(_write(tmp_path, deployment_json))


def test_missing_and_invalid_json(tmp_path):
    with pytest.raises(DeploymentError, match="not found"):
        load_deployment(tmp_path / "nope.json")
    (tmp_path / "bad.json").write_text("{nope")
    with pytest.raises(DeploymentError, match="not valid JSON"):
        load_deployment(tmp_path / "bad.json")


# ------------------------------------------------------------------ on-chain


def _contracts(w3):
    return (w3.eth.contract(address=REGISTRY, abi=list(load_abi("StressRegistry"))),
            w3.eth.contract(address=VAULT, abi=list(load_abi("DemoVault"))),
            w3.eth.contract(address=MARKET, abi=list(load_abi("MockLendingMarket"))))


def test_verify_on_chain_accepts_matching_node(deployment_file, node):
    w3 = Web3(node)
    verify_on_chain(load_deployment(deployment_file), w3, *_contracts(w3))
    assert "eth_sendRawTransaction" not in node.requests  # read-only


def _break_chain_id(n):
    n.chain_id = 84532


def _break_code(n):
    n.code.pop(VAULT.lower())


def _break_bond(n):
    n.set_call(REGISTRY, "BOND()", ["uint256"], [10**15])


def _break_resolver(n):
    n.set_call(REGISTRY, "resolver()", ["address"], [MARKET])


def _break_tolerance(n):
    n.set_call(REGISTRY, "TOLERANCE_BPS()", ["uint16"], [1])


def _break_market_id(n):
    n.set_call(VAULT, "MARKET_ID()", ["bytes32"], [b"\x11" * 32])


def _break_wiring(n):
    n.set_call(MARKET, "vault()", ["address"], [REGISTRY])


@pytest.mark.parametrize("corrupt, message", [
    (_break_chain_id, "connected to chain 84532"),
    (_break_code, "no contract code at vault"),
    (_break_bond, "on-chain BOND is 1000000000000000"),
    (_break_resolver, "on-chain resolver"),
    (_break_tolerance, "on-chain TOLERANCE_BPS is 1"),
    (_break_market_id, "on-chain vault.MARKET_ID"),
    (_break_wiring, "on-chain market.vault"),
])
def test_verify_on_chain_rejects_mismatches(deployment_file, corrupt, message):
    node = FakeNode()
    corrupt(node)
    w3 = Web3(node)
    with pytest.raises(DeploymentError, match=message):
        verify_on_chain(load_deployment(deployment_file), w3, *_contracts(w3))
