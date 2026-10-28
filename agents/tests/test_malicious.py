"""Malicious attester (plan §15.4): only the residual changes, the file stays hash-consistent and
structurally valid, the core verdict is WRONG_RESULT, and nothing is sent without --send."""

import copy
import json

import httpx
import pytest
from stressproof_core import build_replay_report, canonical_bytes, evaluate, keccak256_hex, market_id, parse_strict
from stressproof_core.report import REPLAY_REPORT_KEYS

from stressproof_agents.attester.workflow import AttesterError
from stressproof_agents.common.chain import ChainError
from stressproof_agents.common.deployments import load_deployment
from stressproof_agents.malicious.inflate import TamperError, inflate_residual
from stressproof_agents.malicious.main import cli, run_malicious

from attester_fakes import BASE, FIXTURE_BYTES, FIXTURE_HASH, FIXTURE_R, FakeBackend, expect_claim, make_context
from conftest import TEST_ADDRESS, FakeNode

MARKET = "aave-v3-eth-weth-stable"
INFLATED = inflate_residual(FIXTURE_BYTES)
INFLATED_URI = f"{BASE}/case-files/{INFLATED.evidence_hash}"


def onchain(evidence_hash, claimed):
    return {"evidenceHash": evidence_hash, "marketId": market_id(MARKET), "claimedResidualBadDebt": claimed}


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def ctx(node, deployment_file, backend):
    expect_claim(node, 2, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, TEST_ADDRESS, 1_700_000_200)
    return make_context(node, load_deployment(deployment_file), backend)


def _run(ctx, send=False, from_hash=None, lines=None):
    return run_malicious(ctx, from_hash, "weth-stable-fixture-v1", -3000, send=send,
                         echo=(lines.append if lines is not None else (lambda s: None)))


# ------------------------------------------------------------- tampering


def test_only_the_residual_changes_and_it_is_tripled():
    honest, tampered = parse_strict(FIXTURE_BYTES), parse_strict(INFLATED.raw)
    assert INFLATED.honest_usd8 == FIXTURE_R and INFLATED.inflated_usd8 == 3 * FIXTURE_R
    assert tampered["results"]["residualBadDebtUsd8"] == str(3 * FIXTURE_R)
    restored = copy.deepcopy(tampered)
    restored["results"]["residualBadDebtUsd8"] = honest["results"]["residualBadDebtUsd8"]
    assert canonical_bytes(restored) == FIXTURE_BYTES  # nothing else moved, byte for byte
    for key in ("snapshot", "scenario", "agentRationale", "dataset", "model", "marketId", "dataClass"):
        assert tampered[key] == honest[key]
    for metric in ("debtAtRiskUsd8", "liquidatableAccounts", "liquidationVolumeUsd8"):
        assert tampered["results"][metric] == honest["results"][metric]


def test_tampered_file_is_canonical_and_hash_consistent():
    assert canonical_bytes(parse_strict(INFLATED.raw)) == INFLATED.raw
    assert keccak256_hex(INFLATED.raw) == INFLATED.evidence_hash != FIXTURE_HASH
    assert INFLATED.honest_hash == FIXTURE_HASH


def test_core_verdict_for_the_inflated_claim_is_wrong_result_with_the_honest_counter():
    evaluation = evaluate(INFLATED.raw, onchain(INFLATED.evidence_hash, INFLATED.inflated_usd8))
    assert evaluation.verdict == "WRONG_RESULT"
    assert evaluation.violations == [] and evaluation.hash_matches
    assert evaluation.counter_residual_usd8 == FIXTURE_R
    assert evaluation.recomputed.residual_bad_debt_usd8 == FIXTURE_R
    assert evaluation.claimed_in_file_usd8 == str(3 * FIXTURE_R)


def test_file_claim_disagreeing_with_chain_while_replay_matches_chain_is_evidence_invalid():
    """Developer 2's rule: V-14 fails, but the replay equals the on-chain claim (R)."""
    evaluation = evaluate(INFLATED.raw, onchain(INFLATED.evidence_hash, FIXTURE_R))
    assert evaluation.verdict == "EVIDENCE_INVALID" and evaluation.violation_codes == ["V-14"]
    assert evaluation.counter_residual_usd8 == 0


def test_honest_file_is_a_match():
    evaluation = evaluate(FIXTURE_BYTES, onchain(FIXTURE_HASH, FIXTURE_R))
    assert evaluation.verdict == "MATCH" and evaluation.violations == []


@pytest.mark.parametrize("raw, message", [
    (json.dumps(parse_strict(FIXTURE_BYTES), indent=2).encode(), "not canonical"),
    (b"not json", "not canonical"),
    (canonical_bytes({"results": {}}), "no results.residualBadDebtUsd8"),
    (canonical_bytes({"results": {"residualBadDebtUsd8": 5}}), "not a decimal string"),
])
def test_unusable_honest_input_is_refused(raw, message):
    with pytest.raises(TamperError, match=message):
        inflate_residual(raw)


def test_zero_residual_is_refused():
    zero = parse_strict(FIXTURE_BYTES)
    zero["results"]["residualBadDebtUsd8"] = "0"
    with pytest.raises(TamperError, match="residual bad debt is 0"):
        inflate_residual(canonical_bytes(zero))


# ------------------------------------------------- null replay-report fields


def test_replay_report_has_null_fields_when_replay_did_not_run():
    """For the watcher (D3-6): EVIDENCE_INVALID before replay gives null recomputed/claimedInFileUsd8."""
    junk = b'{"not":"a case file"}'
    evaluation = evaluate(junk, onchain(keccak256_hex(junk), 1))
    report = build_replay_report(
        evaluation, chain_id=31337, registry="0x5FbDB2315678afecb367f032d93F642f64180aa3", claim_id=1,
        evidence_hash=keccak256_hex(junk), fetched_from=f"{BASE}/x", watcher=TEST_ADDRESS,
        replayer_commit="0" * 40, claimed_onchain_usd8=1)
    assert evaluation.verdict == "EVIDENCE_INVALID" and evaluation.recomputed is None
    assert report["recomputed"] is None and report["claimedInFileUsd8"] is None
    assert len(report) == 17 and set(report) == REPLAY_REPORT_KEYS
    assert parse_strict(canonical_bytes(report)) == report  # still canonical with nulls


def test_replay_report_for_the_inflated_claim():
    evaluation = evaluate(INFLATED.raw, onchain(INFLATED.evidence_hash, INFLATED.inflated_usd8))
    report = build_replay_report(
        evaluation, chain_id=31337, registry="0x5FbDB2315678afecb367f032d93F642f64180aa3", claim_id=2,
        evidence_hash=INFLATED.evidence_hash, fetched_from=INFLATED_URI, watcher=TEST_ADDRESS,
        replayer_commit="0" * 40, claimed_onchain_usd8=INFLATED.inflated_usd8)
    assert report["verdict"] == "WRONG_RESULT" and report["violations"] == [] and len(report) == 17
    assert report["recomputed"]["residualBadDebtUsd8"] == str(FIXTURE_R)
    assert report["claimedInFileUsd8"] == report["claimedOnChainUsd8"] == str(3 * FIXTURE_R)


# ---------------------------------------------------------------- workflow


def _nothing_sent(node):
    return node.sent == [] and "eth_sendRawTransaction" not in node.requests


def test_dry_run_stores_and_checks_the_tampered_file_but_sends_nothing(ctx, node, backend):
    lines = []
    result = _run(ctx, lines=lines)
    assert _nothing_sent(node) and result.posted is None and backend.feed == []
    assert result.plan.claimed_usd8 == 3 * FIXTURE_R and result.plan.evidence_hash == INFLATED.evidence_hash
    assert backend.store[INFLATED.evidence_hash] == INFLATED.raw  # stored byte for byte
    assert lines[0].startswith("*** DEMO ONLY") and any("DRY RUN" in line for line in lines)


def test_cli_defaults_to_dry_run():
    params = {p.name: p for p in cli.params}
    assert params["dry_run"].default is True


def test_send_posts_the_inflated_claim(ctx, node, backend):
    result = _run(ctx, send=True)
    assert len(node.sent) == 1 and result.posted.claim_id == 2
    (entry,) = backend.feed
    assert entry["actor"] == "malicious_attester" and entry["kind"] == "CLAIM_POSTED"
    assert entry["data"]["claimedUsd8"] == str(3 * FIXTURE_R) and entry["data"]["honestUsd8"] == str(FIXTURE_R)
    assert entry["data"]["demo"] is True


def test_from_hash_starts_from_the_stored_honest_file(ctx, node, backend):
    _run(ctx, from_hash=FIXTURE_HASH)
    assert backend.posted("/stress/run") == []
    fetched = [r for r in backend.requests if r.method == "GET"]
    assert fetched[0].url.path == f"/case-files/{FIXTURE_HASH}"


def test_backend_storing_under_another_hash_is_refused(ctx, node, backend):
    backend.store_override = lambda r: httpx.Response(201, json={
        "evidenceHash": "0x" + "ab" * 32, "caseFileURI": f"{BASE}/case-files/0x{'ab' * 32}"})
    with pytest.raises(AttesterError, match="stored the file as"):
        _run(ctx, send=True)
    assert _nothing_sent(node)


def test_tampered_file_served_differently_is_refused(ctx, node, backend):
    backend.serve_override[INFLATED.evidence_hash] = FIXTURE_BYTES
    with pytest.raises(AttesterError, match="hashes to"):
        _run(ctx, send=True)
    assert _nothing_sent(node)


def test_dishonest_starting_file_is_refused(ctx, node, backend):
    """Starting from a file that is itself wrong would not demonstrate the honest-vs-3x contrast."""
    wrong = parse_strict(FIXTURE_BYTES)
    wrong["results"]["residualBadDebtUsd8"] = str(FIXTURE_R + 5)
    raw = canonical_bytes(wrong)
    backend.store[keccak256_hex(raw)] = raw
    with pytest.raises(AttesterError, match="expected MATCH"):
        _run(ctx, from_hash=keccak256_hex(raw))
    assert _nothing_sent(node)


def test_unsupported_chain_is_refused(deployment_file):
    with pytest.raises(ChainError, match="refusing to use chain 1"):
        make_context(FakeNode(chain_id=1), load_deployment(deployment_file), FakeBackend())
