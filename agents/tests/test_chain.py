"""ChainClient against the fake node: chain checks, reads, transactions, nonces, fees, reverts, events."""

import threading

import pytest
from eth_account.typed_transactions import TypedTransaction
from web3 import Web3

from stressproof_agents.common.chain import ChainClient, ChainError, TransactionReverted, TxPolicy
from stressproof_agents.common.config import Secret
from stressproof_agents.common.deployments import load_deployment
from stressproof_agents.common.nonce import NonceManager
from stressproof_agents.common.revert import ErrorDecoder, revert_data_from
from stressproof_agents.common.abi import load_abi

from conftest import (CORE_MARKET_ID, REGISTRY, TEST_ADDRESS, TEST_KEY, FakeNode, claim_posted_log,
                      error_data)

EVIDENCE = "0x" + "aa" * 32


def _client(node, deployment_file, signer=True, policy=TxPolicy(receipt_timeout_sec=2, receipt_poll_sec=0.01)):
    key = Secret(TEST_KEY, "WATCHER_PK") if signer else None
    return ChainClient(Web3(node), load_deployment(deployment_file), key, policy)


def _post_claim(client, claimed=600_000_000_003):
    return client.registry.functions.postClaim(bytes.fromhex(CORE_MARKET_ID[2:]), claimed,
                                               bytes.fromhex(EVIDENCE[2:]), "http://127.0.0.1:8000/x")


# ------------------------------------------------------------------- chains


def test_connects_and_verifies_the_deployment(node, deployment_file):
    client = _client(node, deployment_file)
    client.verify_deployment()
    assert client.address == TEST_ADDRESS
    assert TEST_KEY not in repr(client) and TEST_KEY[2:] not in repr(client)


def test_chain_id_mismatch_is_refused(deployment_file):
    with pytest.raises(ChainError, match="connected to chain 84532, deployments file is for 31337"):
        _client(FakeNode(chain_id=84532), deployment_file)


@pytest.mark.parametrize("chain_id", [1, 8453, 11155111])
def test_mainnet_and_unknown_chains_are_refused(deployment_file, chain_id):
    with pytest.raises(ChainError, match=f"refusing to use chain {chain_id}"):
        _client(FakeNode(chain_id=chain_id), deployment_file)


def test_unreachable_rpc_is_a_chain_error(deployment_file):
    with pytest.raises(ChainError, match="cannot reach the RPC endpoint"):
        ChainClient.connect("http://127.0.0.1:1", load_deployment(deployment_file), timeout_sec=1)


def test_read_only_client_cannot_transact(node, deployment_file):
    client = _client(node, deployment_file, signer=False)
    assert client.address is None
    with pytest.raises(ChainError, match="no signing key"):
        client.transact(_post_claim(client), value=10**16)


def test_reads_and_block_timestamp(node, deployment_file):
    client = _client(node, deployment_file)
    assert client.call(client.registry.functions.BOND()) == 10**16
    assert client.latest_block_timestamp() == 1_700_000_010


def test_reverting_call_is_decoded(node, deployment_file):
    node.calls[(REGISTRY.lower(), error_data("status(uint256)")[:10])] = (
        "revert:" + error_data("InvalidState(uint8)", ["uint8"], [2]))
    client = _client(node, deployment_file)
    with pytest.raises(TransactionReverted) as exc:
        client.call(client.registry.functions.status(1))
    assert exc.value.error.name == "InvalidState" and exc.value.error.args == (2,)


# ------------------------------------------------------------- transactions


def test_transact_builds_eip1559_tx_with_fees_gas_and_chain_id(node, deployment_file):
    client = _client(node, deployment_file)
    result = client.transact(_post_claim(client), value=10**16)
    sent = node.sent[-1]
    assert sent["from"] == TEST_ADDRESS.lower() and sent["nonce"] == 0 and sent["chainId"] == 31337
    assert sent["type"] == 2 and sent["value"] == 10**16
    assert sent["gas"] == 120_000  # estimate 100_000 + 20%
    assert sent["maxPriorityFeePerGas"] == 10**9 and sent["maxFeePerGas"] == 2 * 7 + 10**9
    assert result.tx_hash == sent["hash"] and result.block_number == node.block_number


def test_nonces_increase_locally_without_asking_the_node_again(node, deployment_file):
    client = _client(node, deployment_file)
    for _ in range(3):
        client.transact(_post_claim(client), value=10**16)
    assert [tx["nonce"] for tx in node.sent] == [0, 1, 2]
    assert node.requests.count("eth_getTransactionCount") == 1


def test_nonce_starts_from_the_nodes_pending_count(node, deployment_file):
    node.nonces[TEST_ADDRESS.lower()] = 5
    client = _client(node, deployment_file)
    client.transact(_post_claim(client), value=10**16)
    assert node.sent[-1]["nonce"] == 5


def test_nonce_too_low_triggers_one_resync_and_retry(node, deployment_file):
    client = _client(node, deployment_file)
    client.transact(_post_claim(client), value=10**16)  # nonce 0
    node.nonces[TEST_ADDRESS.lower()] = 4  # another process used this key (plan forbids it; we recover)
    client.transact(_post_claim(client), value=10**16)
    assert [tx["nonce"] for tx in node.sent] == [0, 4]


def test_revert_in_gas_estimation_is_decoded_and_uses_no_nonce(node, deployment_file):
    node.revert_next_estimate = error_data("WrongBond(uint256,uint256)", ["uint256", "uint256"], [1, 10**16])
    client = _client(node, deployment_file)
    with pytest.raises(TransactionReverted) as exc:
        client.transact(_post_claim(client), value=1)
    assert str(exc.value.error) == f"WrongBond(1, {10**16})"
    assert node.sent == []
    client.transact(_post_claim(client), value=10**16)
    assert node.sent[-1]["nonce"] == 0  # the failed attempt did not burn a nonce


def test_failed_receipt_raises_with_tx_hash(node, deployment_file):
    node.fail_next_receipt = True
    client = _client(node, deployment_file)
    with pytest.raises(TransactionReverted) as exc:
        client.transact(_post_claim(client), value=10**16)
    assert exc.value.tx_hash == node.sent[-1]["hash"]


def test_receipt_timeout_is_a_chain_error(node, deployment_file):
    client = _client(node, deployment_file, policy=TxPolicy(receipt_timeout_sec=0.05, receipt_poll_sec=0.01))
    node._eth_getTransactionReceipt = lambda params: None  # never mined
    with pytest.raises(ChainError, match="no receipt"):
        client.transact(_post_claim(client), value=10**16)


def test_signed_transaction_never_contains_the_key(node, deployment_file):
    client = _client(node, deployment_file)
    client.transact(_post_claim(client), value=10**16)
    raw_txs = [str(tx) for tx in node.sent]
    assert all(TEST_KEY[2:] not in t for t in raw_txs)


# ------------------------------------------------------------------- events


def test_events_are_parsed_from_receipts_and_logs(node, deployment_file):
    node.logs.append(claim_posted_log(7, TEST_ADDRESS, 600_000_000_003, EVIDENCE, "ipfs://cid", 1_700_000_130))
    client = _client(node, deployment_file)
    result = client.transact(_post_claim(client), value=10**16)
    (event,) = client.parse_events(result.receipt, "StressRegistry", "ClaimPosted")
    assert event.args.claimId == 7 and event.args.attester == TEST_ADDRESS
    assert event.args.claimedResidualBadDebt == 600_000_000_003 and event.args.caseFileURI == "ipfs://cid"
    assert "0x" + event.args.marketId.hex() == CORE_MARKET_ID
    assert client.parse_events(result.receipt, "StressRegistry", "ClaimChallenged") == ()
    (logged,) = client.get_events("ClaimPosted", from_block=1)
    assert logged.args.claimId == 7 and logged.args.challengeDeadline == 1_700_000_130


# ------------------------------------------------------------ error decoder


def test_error_decoder_knows_every_contract_error():
    decoder = ErrorDecoder([load_abi("StressRegistry"), load_abi("DemoVault"), load_abi("MockLendingMarket")])
    assert len(decoder.known_errors) == 25
    assert str(decoder.decode(error_data("LtvTooHigh(uint256,uint256)", ["uint256"] * 2, [7000, 5000]))) == \
        "LtvTooHigh(7000, 5000)"
    assert decoder.decode(error_data("NotFinalized()")).name == "NotFinalized"
    assert decoder.decode(error_data("Error(string)", ["string"], ["boom"])).args == ("boom",)
    assert decoder.decode(error_data("Panic(uint256)", ["uint256"], [0x11])).args == (0x11,)
    assert decoder.decode("0xdeadbeef") is None and decoder.decode(None) is None and decoder.decode("0x") is None


def test_revert_data_is_extracted_from_exceptions():
    class E(Exception):
        def __init__(self, data):
            self.data = data
    assert revert_data_from(E("0x1234")) == "0x1234"
    assert revert_data_from(E({"data": "0xabcd"})) == "0xabcd"
    assert revert_data_from(E(b"\x12\x34")) == "0x1234"
    assert revert_data_from(E(None)) is None


# --------------------------------------------------------------- nonce unit


def test_nonce_manager_release_and_concurrency():
    fetches = []
    manager = NonceManager(lambda: fetches.append(1) or 10)
    assert manager.reserve() == 10
    manager.release(10)
    assert manager.reserve() == 10  # released latest nonce is reused
    a = manager.reserve()
    manager.release(10)  # not the latest: forces a resync next time
    assert manager.reserve() == 10 and len(fetches) == 2 and a == 11

    shared = NonceManager(lambda: 0)
    seen = []
    threads = [threading.Thread(target=lambda: seen.append(shared.reserve())) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(seen) == list(range(50))
