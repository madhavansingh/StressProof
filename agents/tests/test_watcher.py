"""Watcher (plan §15.2): verdicts from core, challenge reasons, reports, deadlines, skips, retries,
restarts, outcomes and withdrawals. Everything runs against the fake node, registry and backend."""

import json
import re
from pathlib import Path

import httpx
import pytest
from stressproof_core import keccak256_hex, parse_strict
from stressproof_core.report import REPLAY_REPORT_KEYS

from stressproof_agents.common.chain import ChainError
from stressproof_agents.common.deployments import load_deployment
from stressproof_agents.common.state import WatcherState
from stressproof_agents.malicious.inflate import inflate_residual
from stressproof_agents.watcher import poller as poller_module
from stressproof_agents.watcher.dry_run import DryRunProcessor
from stressproof_agents.watcher.main import cli, replayer_commit
from stressproof_agents.watcher.outcomes import settle
from stressproof_agents.watcher.poller import Watcher
from stressproof_agents.watcher.processor import REASON_BY_VERDICT, ClaimProcessor

from attester_fakes import BASE, FIXTURE_BYTES, FIXTURE_HASH, FIXTURE_R, FakeBackend, make_context
from conftest import REGISTRY, TEST_ADDRESS, FakeNode, error_data, selector
from watcher_fakes import ATTESTER, FakeRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT = "c" * 40
BOND = 10**16
NOW = 1_700_000_010  # FakeNode block 10
INFLATED = inflate_residual(FIXTURE_BYTES)
HONEST_URI = f"{BASE}/case-files/{FIXTURE_HASH}"
INFLATED_URI = f"{BASE}/case-files/{INFLATED.evidence_hash}"


@pytest.fixture
def world(tmp_path, node, deployment_file):
    backend = FakeBackend()
    backend.store[INFLATED.evidence_hash] = INFLATED.raw
    ctx = make_context(node, load_deployment(deployment_file), backend)
    registry = FakeRegistry(node)
    state = WatcherState(tmp_path / "watcher.sqlite")
    processor = ClaimProcessor(ctx.client, ctx.fetcher, ctx.backend, state, ctx.feed, COMMIT, BOND)
    watcher = Watcher(ctx.client, state, processor, ctx.feed, start_block=1, workers=2)
    yield {"node": node, "backend": backend, "ctx": ctx, "registry": registry, "state": state,
           "processor": processor, "watcher": watcher, "tmp": tmp_path}
    state.close()


def _post(world, claim_id, claimed, evidence_hash, uri, deadline=NOW + 200, **kw):
    world["registry"].add(claim_id, claimed, evidence_hash, uri, deadline, **kw)


def _report(world, report_hash):
    return json.loads(world["backend"].reports[report_hash])


def _kinds(world):
    return [e["kind"] for e in world["backend"].feed]


# --------------------------------------------------------------- verdicts


def test_honest_claim_matches_and_nothing_is_sent(world):
    _post(world, 1, FIXTURE_R, FIXTURE_HASH, HONEST_URI)
    result = world["watcher"].poll_once()
    assert result.new_claims == (1,) and result.errors == ()
    assert world["state"].get(1).state == "MATCH"
    assert world["node"].sent == [] and world["backend"].reports == {}
    assert _kinds(world) == ["FILE_FETCHED", "HASH_OK", "REPLAY_MATCH"]


def test_inflated_claim_is_challenged_with_reason_1_and_the_honest_counter(world):
    _post(world, 2, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI)
    world["watcher"].poll_once()
    (challenge,) = world["registry"].challenges
    assert challenge["reason"] == 1 and challenge["counter"] == FIXTURE_R and challenge["value"] == BOND
    record = world["state"].get(2)
    assert record.state == "CHALLENGED" and record.verdict == "WRONG_RESULT" and record.recomputed_usd8 == FIXTURE_R
    report = _report(world, challenge["reportHash"])
    assert set(report) == REPLAY_REPORT_KEYS and len(report) == 17
    assert report["verdict"] == "WRONG_RESULT" and report["violations"] == [] and report["hashMatches"] is True
    assert report["recomputed"]["residualBadDebtUsd8"] == str(FIXTURE_R)
    assert report["claimedOnChainUsd8"] == report["claimedInFileUsd8"] == str(3 * FIXTURE_R)
    assert report["claimId"] == "2" and report["watcher"] == TEST_ADDRESS and report["replayerCommit"] == COMMIT
    assert report["caseFileCopyURI"] == INFLATED_URI  # C-19 copy stored for the resolver
    assert challenge["uri"].endswith(challenge["reportHash"])
    assert "CHALLENGE_SENT" in _kinds(world) and "REPLAY_MISMATCH" in _kinds(world)


def test_hash_mismatch_is_challenged_as_evidence_invalid_with_null_report_fields(world):
    _post(world, 3, FIXTURE_R, "0x" + "ab" * 32, HONEST_URI)  # on-chain hash does not match the served bytes
    world["watcher"].poll_once()
    (challenge,) = world["registry"].challenges
    assert challenge["reason"] == 2 and challenge["counter"] == 0
    report = _report(world, challenge["reportHash"])
    assert report["verdict"] == "EVIDENCE_INVALID" and report["hashMatches"] is False
    assert report["recomputed"] is None and report["claimedInFileUsd8"] is None and len(report) == 17
    assert report["caseFileCopyURI"] == ""  # no copy of bytes that do not match
    assert "HASH_MISMATCH" in _kinds(world)


def test_malformed_evidence_is_evidence_invalid(world):
    junk = b'{"not":"a case file"}'
    world["backend"].store[keccak256_hex(junk)] = junk
    _post(world, 4, 5, keccak256_hex(junk), f"{BASE}/case-files/{keccak256_hex(junk)}")
    world["watcher"].poll_once()
    (challenge,) = world["registry"].challenges
    assert challenge["reason"] == 2 and challenge["counter"] == 0
    report = _report(world, challenge["reportHash"])
    assert report["hashMatches"] is True and report["recomputed"] is None and report["violations"]
    assert "VALIDATION_FAILED" in _kinds(world)


def test_file_disagreeing_with_chain_but_replay_matching_chain_is_evidence_invalid(world):
    """Developer 2's rule: tampered file says 3R, the on-chain claim is R, the replay gives R."""
    _post(world, 5, FIXTURE_R, INFLATED.evidence_hash, INFLATED_URI)
    world["watcher"].poll_once()
    (challenge,) = world["registry"].challenges
    assert challenge["reason"] == 2 and challenge["counter"] == 0
    assert _report(world, challenge["reportHash"])["violations"] == ["V-14"]


def test_reason_codes_match_the_contract_enum():
    source = (REPO_ROOT / "contracts" / "src" / "IStressRegistry.sol").read_text()
    members = re.search(r"enum Reason\s*\{([^}]*)\}", source).group(1).replace(" ", "").replace("\n", "").split(",")
    assert members.index("WRONG_RESULT") == REASON_BY_VERDICT["WRONG_RESULT"] == 1
    assert members.index("EVIDENCE_INVALID") == REASON_BY_VERDICT["EVIDENCE_INVALID"] == 2


# ---------------------------------------------------------------- skipping


def test_own_claims_are_never_challenged(world):
    _post(world, 6, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, attester=TEST_ADDRESS)
    world["watcher"].poll_once()
    assert world["state"].get(6).state == "SKIPPED" and world["node"].sent == []
    assert world["backend"].requests == [] or all(r.url.path == "/feed" for r in world["backend"].requests)


def test_closed_window_is_skipped(world):
    _post(world, 7, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, deadline=NOW)  # now >= deadline
    world["watcher"].poll_once()
    assert world["state"].get(7).state == "SKIPPED" and world["node"].sent == []


def test_claim_challenged_by_someone_else_before_we_act_is_skipped(world):
    _post(world, 8, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI)
    world["registry"].flip_after_reads[8] = 1  # first read Pending, the re-read before sending shows Challenged
    world["watcher"].poll_once()
    assert world["state"].get(8).state == "SKIPPED" and world["registry"].challenges == []


def test_challenge_that_reverts_is_recorded_as_failed(world):
    _post(world, 9, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI)
    world["node"].revert_estimate_for[selector("challenge(uint256,uint8,uint256,string,bytes32)")] = (
        error_data("ChallengeWindowClosed()"))
    world["watcher"].poll_once()
    record = world["state"].get(9)
    assert record.state == "CHALLENGE_FAILED" and "ChallengeWindowClosed" in record.error
    assert world["node"].sent == [] and "CHALLENGE_FAILED" in _kinds(world)


# ------------------------------------------------------ fetching and timing


def test_fetch_failure_waits_while_there_is_time_then_challenges_near_the_deadline(world):
    missing = "0x" + "cd" * 32
    _post(world, 10, FIXTURE_R, missing, f"{BASE}/case-files/{missing}", deadline=NOW + 100)
    world["watcher"].poll_once()
    assert world["state"].get(10).state == "FETCHING" and world["node"].sent == []  # 90 s left: retry later
    world["node"].block_number += 75  # 25 s left, under the 30 s margin
    world["watcher"].poll_once()
    (challenge,) = world["registry"].challenges
    assert challenge["reason"] == 2 and challenge["counter"] == 0
    report = _report(world, challenge["reportHash"])
    assert report["hashMatches"] is False and report["fetchedFrom"] == f"{BASE}/case-files/{missing}"
    assert _kinds(world).count("FETCH_FAILED") == 2


def test_backend_outage_for_reports_retries_on_the_next_poll(world):
    _post(world, 11, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI)
    world["backend"].report_override = lambda r: httpx.Response(503)
    result = world["watcher"].poll_once()
    assert result.errors and "HTTP 503" in result.errors[0][1]
    assert world["state"].get(11).state == "FETCHING" and world["node"].sent == []
    assert "ERROR" in _kinds(world)
    world["backend"].report_override = None
    assert world["watcher"].poll_once().errors == ()
    assert world["state"].get(11).state == "CHALLENGED" and len(world["registry"].challenges) == 1


# -------------------------------------------------------------- restarts


def test_restart_after_a_challenge_landed_does_not_resend(world, deployment_file):
    _post(world, 12, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI)
    node = world["node"]
    node._eth_getTransactionReceipt = lambda params: None  # the tx lands but the receipt never arrives
    world["processor"]._client._policy = world["processor"]._client._policy.__class__(
        receipt_timeout_sec=0.05, receipt_poll_sec=0.01)
    result = world["watcher"].poll_once()
    assert result.errors and "no receipt" in result.errors[0][1]
    assert world["state"].get(12).state == "CHALLENGE_SENDING" and len(world["registry"].challenges) == 1

    # Restart: a new processor and watcher on the same database.
    state2 = WatcherState(world["tmp"] / "watcher.sqlite")
    ctx = world["ctx"]
    processor2 = ClaimProcessor(ctx.client, ctx.fetcher, ctx.backend, state2, ctx.feed, COMMIT, BOND)
    Watcher(ctx.client, state2, processor2, ctx.feed, start_block=1).poll_once()
    assert state2.get(12).state == "CHALLENGED"
    assert len(world["registry"].challenges) == 1  # recognised on chain, not sent twice
    state2.close()


def test_restart_resumes_the_cursor_and_does_not_reingest(world):
    _post(world, 13, FIXTURE_R, FIXTURE_HASH, HONEST_URI, block=5)
    first = world["watcher"].poll_once()
    assert first.new_claims == (13,) and first.cursor == world["node"].block_number
    state2 = WatcherState(world["tmp"] / "watcher.sqlite")
    ctx = world["ctx"]
    w2 = Watcher(ctx.client, state2, ClaimProcessor(ctx.client, ctx.fetcher, ctx.backend, state2, None, COMMIT, BOND),
                 None, start_block=1)
    world["node"].block_number += 3
    _post(world, 14, FIXTURE_R, FIXTURE_HASH, HONEST_URI, block=world["node"].block_number)
    second = w2.poll_once()
    assert second.new_claims == (14,)  # claim 13 is not re-read: the cursor survived the restart
    assert int(world["node"].log_queries[-1]["fromBlock"], 16) == first.cursor + 1
    state2.close()


def test_large_block_ranges_are_read_in_chunks(world, monkeypatch):
    monkeypatch.setattr(poller_module, "LOG_RANGE", 4)
    _post(world, 15, FIXTURE_R, FIXTURE_HASH, HONEST_URI, block=9)
    world["watcher"].poll_once()
    ranges = [(int(q["fromBlock"], 16), int(q["toBlock"], 16)) for q in world["node"].log_queries]
    assert ranges == [(1, 4), (5, 8), (9, 10)] and world["state"].get(15) is not None


def test_one_failing_claim_does_not_block_others(world):
    _post(world, 16, FIXTURE_R, FIXTURE_HASH, HONEST_URI)
    _post(world, 17, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI)
    world["node"].call_handlers[(REGISTRY.lower(), selector("claim(uint256)"))] = (
        lambda data, original=world["node"].call_handlers[(REGISTRY.lower(), selector("claim(uint256)"))]:
        "revert:0x" if int(data[10:], 16) == 16 else original(data))
    result = world["watcher"].poll_once()
    assert [e[0] for e in result.errors] == [16]
    assert world["state"].get(17).state == "CHALLENGED"


# ---------------------------------------------------------------- outcomes


@pytest.mark.parametrize("on_chain_state, outcome, withdraws", [(4, "WITHDRAWN", True), (5, "WITHDRAWN", True),
                                                                (3, "LOST", False)])
def test_outcomes_and_withdrawal(world, on_chain_state, outcome, withdraws):
    _post(world, 20, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI)
    world["watcher"].poll_once()
    assert world["state"].get(20).state == "CHALLENGED"
    world["watcher"].poll_once()  # resolver has not acted yet
    assert world["state"].get(20).state == "CHALLENGED"
    world["registry"].set_state(20, on_chain_state)
    world["registry"].credit = 2 * BOND if on_chain_state == 4 else BOND
    world["watcher"].poll_once()
    assert world["state"].get(20).state == outcome
    assert world["registry"].withdrawals == (1 if withdraws else 0)


def test_payout_already_withdrawn_is_not_withdrawn_again(world):
    _post(world, 21, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI)
    world["watcher"].poll_once()
    world["registry"].set_state(21, 4)
    world["registry"].credit = 0  # collected together with another claim's payout
    record = settle(world["ctx"].client, world["state"], None, world["state"].get(21))
    assert record.state == "WITHDRAWN" and world["registry"].withdrawals == 0


# ---------------------------------------------------------------- dry run


def test_dry_run_processor_never_sends_or_stores(world):
    _post(world, 30, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI)
    _post(world, 31, FIXTURE_R, FIXTURE_HASH, HONEST_URI)
    ctx = world["ctx"]
    dry_state = WatcherState(world["tmp"] / "dry.sqlite")
    dry = DryRunProcessor(ctx.client, ctx.fetcher, dry_state)
    Watcher(ctx.client, dry_state, dry, None, start_block=1).poll_once()
    assert world["node"].sent == [] and world["backend"].reports == {}
    assert all(r.method == "GET" for r in world["backend"].requests)
    assert dry.decisions[30].startswith("would challenge: WRONG_RESULT (reason 1, counter 200000000001")
    assert dry.decisions[31] == "MATCH: no challenge"
    dry_state.close()


def test_cli_defaults_to_dry_run():
    params = {p.name: p for p in cli.params}
    assert params["dry_run"].default is True


def test_replayer_commit():
    assert replayer_commit({"GIT_COMMIT": COMMIT}) == COMMIT
    assert re.fullmatch(r"[0-9a-f]{40}", replayer_commit({}, REPO_ROOT))
    from stressproof_agents.common.config import ConfigError
    with pytest.raises(ConfigError, match="GIT_COMMIT must be"):
        replayer_commit({"GIT_COMMIT": "abc"})
