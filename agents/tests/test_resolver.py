"""Resolver CLI (plan §15.3, C-19): its own core-based decision, evidence sources, authorization,
states, deadline boundaries, duplicates, RPC failures and dry-run safety. Fakes only; nothing real is sent."""

import json

import httpx
import pytest
from click.testing import CliRunner
from stressproof_core import build_replay_report, canonical_bytes, evaluate, keccak256_hex, market_id, parse_strict
from stressproof_core.report import REPLAY_REPORT_KEYS
from web3 import Web3

from stressproof_agents.common.chain import ChainClient, ChainError, TransactionReverted, TxPolicy
from stressproof_agents.common.deployments import load_deployment
from stressproof_agents.malicious.inflate import inflate_residual
from stressproof_agents.resolver.actions import NothingToDo, Refused
from stressproof_agents.resolver.cli import ResolverContext, cli, cmd_check, cmd_expire, cmd_resolve, cmd_show

from attester_fakes import BASE, FIXTURE_BYTES, FIXTURE_HASH, FIXTURE_R, FakeBackend, make_context
from conftest import REGISTRY, RESOLVER, TEST_ADDRESS, TEST_KEY, error_data, selector
from watcher_fakes import ATTESTER, FakeRegistry

NOW = 1_700_000_010  # FakeNode block 10
WATCHER = "0x90F79bf6EB2c4f870365E785982E1f101E93b906"
COMMIT = "c" * 40
INFLATED = inflate_residual(FIXTURE_BYTES)
HONEST_URI = f"{BASE}/case-files/{FIXTURE_HASH}"
INFLATED_URI = f"{BASE}/case-files/{INFLATED.evidence_hash}"


@pytest.fixture
def rw(node, deployment_file):
    backend = FakeBackend()
    backend.store[INFLATED.evidence_hash] = INFLATED.raw
    actx = make_context(node, load_deployment(deployment_file), backend)
    registry = FakeRegistry(node)
    node.set_call(REGISTRY, "resolver()", ["address"], [TEST_ADDRESS])  # this signer is the designated resolver
    ctx = ResolverContext(actx.settings, actx.deployment, actx.client, actx.fetcher, actx.feed, COMMIT)
    return {"node": node, "backend": backend, "registry": registry, "ctx": ctx, "lines": []}


def dispute(rw, claim_id, claimed, evidence_hash, uri, reason, counter, resolution_deadline=NOW + 300,
            report=True, attester=ATTESTER, challenger=WATCHER):
    """A claim challenged by a watcher, with the watcher's report built by the core library."""
    rw["registry"].add(claim_id, claimed, evidence_hash, uri, NOW - 1, attester=attester)
    report_uri, report_hash = "", "0x" + "00" * 32
    if report:
        raw = rw["backend"].store.get(evidence_hash, b"")
        ev = evaluate(raw, {"evidenceHash": evidence_hash, "marketId": market_id("aave-v3-eth-weth-stable"),
                            "claimedResidualBadDebt": claimed})
        rep = canonical_bytes(build_replay_report(
            ev, chain_id=31337, registry=REGISTRY, claim_id=claim_id, evidence_hash=evidence_hash,
            fetched_from=uri, watcher=WATCHER, replayer_commit=COMMIT, claimed_onchain_usd8=claimed,
            case_file_copy_uri=uri if ev.hash_matches else ""))
        report_hash = keccak256_hex(rep)
        rw["backend"].reports[report_hash] = rep
        report_uri = f"{BASE}/replay-reports/{report_hash}"
    rw["registry"].challenged(claim_id, challenger, reason, counter, report_uri, report_hash, resolution_deadline)


def check(rw, claim_id, **kw):
    return cmd_check(rw["ctx"], claim_id, rw["lines"].append, **kw)


def resolve(rw, claim_id, send=False, yes=False, typed=None):
    calls = []

    def prompt(text):
        calls.append(text)
        return typed or ""

    out = cmd_resolve(rw["ctx"], claim_id, send, yes, rw["lines"].append, prompt=prompt)
    return out, calls


def nothing_sent(rw):
    return rw["node"].sent == [] and "eth_sendRawTransaction" not in rw["node"].requests


def text(rw):
    return "\n".join(rw["lines"])


# ------------------------------------------------------------------ decisions


def test_inflated_claim_challenge_is_upheld(rw):
    dispute(rw, 1, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    result = check(rw, 1)
    assert result.evaluation.verdict == "WRONG_RESULT" and result.upheld and result.decision == "UPHOLD"
    assert result.evidence_source.name == "caseFileURI"
    assert result.report_check.hash_ok and result.report_check.differences == ()
    assert nothing_sent(rw)


def test_honest_claim_wrongly_challenged_is_rejected(rw):
    dispute(rw, 2, FIXTURE_R, FIXTURE_HASH, HONEST_URI, reason=1, counter=FIXTURE_R + 1)
    result = check(rw, 2)
    assert result.evaluation.verdict == "MATCH" and not result.upheld and result.decision == "REJECT"
    assert any("on-chain counter" in d for d in result.report_check.differences)  # shown, not used


def test_hash_mismatch_everywhere_is_upheld_as_evidence_invalid(rw):
    bogus = "0x" + "ab" * 32
    dispute(rw, 3, FIXTURE_R, bogus, HONEST_URI, reason=2, counter=0)
    result = check(rw, 3)
    assert result.evidence_source is None and result.evaluation.verdict == "EVIDENCE_INVALID" and result.upheld
    assert all("hash mismatch" in a.outcome or "fetch failed" in a.outcome for a in result.attempts)
    assert "evidence unavailable" in text(rw)


def test_malformed_evidence_with_matching_hash_is_upheld(rw):
    junk = b'{"not":"a case file"}'
    rw["backend"].store[keccak256_hex(junk)] = junk
    dispute(rw, 4, 5, keccak256_hex(junk), f"{BASE}/case-files/{keccak256_hex(junk)}", reason=2, counter=0)
    result = check(rw, 4)
    assert result.evidence_source is not None and result.evaluation.verdict == "EVIDENCE_INVALID" and result.upheld
    assert result.evaluation.recomputed is None


def test_c19_evidence_from_the_challenger_copy_counts_as_retrievable(rw):
    """The attester's host is down, but the watcher's cached copy matches: the replay decides (MATCH)."""
    dispute(rw, 5, FIXTURE_R, FIXTURE_HASH, HONEST_URI, reason=2, counter=0)
    report = json.loads(rw["backend"].reports[rw["registry"].claims[5]["reportHash"]])
    copy_uri = report["caseFileCopyURI"]
    rw["registry"].claims[5]["uri"] = "https://attester-host.example/down"  # primary source unreachable
    rw["ctx"] = rw["ctx"].__class__(**{**rw["ctx"].__dict__, "fetcher": _fetcher_blocking(rw, "attester-host.example")})
    result = check(rw, 5)
    assert result.evidence_source.uri == copy_uri and result.evaluation.verdict == "MATCH" and not result.upheld


def test_backend_copy_is_the_last_fallback(rw):
    dispute(rw, 6, FIXTURE_R, FIXTURE_HASH, "https://attester-host.example/gone", reason=2, counter=0, report=False)
    rw["ctx"] = rw["ctx"].__class__(**{**rw["ctx"].__dict__, "fetcher": _fetcher_blocking(rw, "attester-host.example")})
    result = check(rw, 6)
    assert [a.name for a in result.attempts] == ["caseFileURI", "backend copy"]
    assert result.evidence_source.name == "backend copy" and result.evaluation.verdict == "MATCH"
    assert "claim has no replay report URI" in result.report_check.problems


def test_tampered_challenger_report_is_noted_but_does_not_decide(rw):
    dispute(rw, 7, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    h = rw["registry"].claims[7]["reportHash"]
    rw["backend"].reports[h] = b'{"tampered":true}'
    result = check(rw, 7)
    assert not result.report_check.hash_ok and result.upheld  # decision from the resolver's own replay


def test_backend_down_for_reports_and_copies(rw):
    dispute(rw, 8, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    rw["backend"].reports.clear()
    result = check(rw, 8)
    assert not result.report_check.available and result.upheld


def test_report_out_writes_the_resolvers_own_17_key_report(rw, tmp_path):
    bogus = "0x" + "ab" * 32
    dispute(rw, 9, FIXTURE_R, bogus, HONEST_URI, reason=2, counter=0)
    out = tmp_path / "report.json"
    check(rw, 9, report_out=out)
    report = parse_strict(out.read_bytes())
    assert set(report) == REPLAY_REPORT_KEYS and report["verdict"] == "EVIDENCE_INVALID"
    assert report["recomputed"] is None and report["claimedInFileUsd8"] is None and report["watcher"] == TEST_ADDRESS


def _fetcher_blocking(rw, host):
    """Same fetcher, but `host` refuses connections."""
    from stressproof_agents.common.fetch import EvidenceFetcher

    backend = rw["backend"]

    def transport(request):
        if request.headers.get("host") == host:
            raise httpx.ConnectError("connection refused")
        return backend(request)

    def resolver(h, port):
        return ["127.0.0.1"] if h in ("127.0.0.1", "localhost") else ["93.184.215.14"]

    return EvidenceFetcher(rw["ctx"].settings.fetch, resolver=resolver, transport=httpx.MockTransport(transport),
                           sleep=lambda s: None)


# -------------------------------------------------------------------- show


def test_show_prints_dispute_details_read_only(rw, deployment_file):
    dispute(rw, 10, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    read_only = ChainClient(Web3(rw["node"]), load_deployment(deployment_file), None)
    ctx = rw["ctx"].__class__(**{**rw["ctx"].__dict__, "client": read_only})
    claim = cmd_show(ctx, 10, rw["lines"].append)
    assert claim.state_name == "Challenged" and claim.reason_name == "WRONG_RESULT"
    out = text(rw)
    assert "Challenged" in out and "300s left" in out and WATCHER in out and nothing_sent(rw)
    assert TEST_KEY not in out and TEST_KEY[2:] not in out


# ----------------------------------------------------------------- resolve


def test_resolve_is_a_dry_run_by_default(rw):
    dispute(rw, 11, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    (_, sent), prompts = resolve(rw, 11)
    assert sent is None and prompts == [] and nothing_sent(rw) and rw["backend"].feed == []
    assert "DRY RUN: would send resolve(11, true)" in text(rw)


def test_resolve_with_send_and_typed_confirmation(rw):
    dispute(rw, 12, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    (_, sent), prompts = resolve(rw, 12, send=True, typed="UPHOLD 12")
    assert prompts == ["Type 'UPHOLD 12' to confirm"]
    assert rw["registry"].resolutions == [{"claimId": 12, "upheld": True, "from": TEST_ADDRESS.lower()}]
    assert rw["registry"].claims[12]["state"] == 4 and sent.tx_hash == rw["node"].sent[0]["hash"]
    assert [e["kind"] for e in rw["backend"].feed] == ["RESOLVER_VERDICT", "RESOLVED"]


def test_reject_decision_sends_upheld_false(rw):
    dispute(rw, 13, FIXTURE_R, FIXTURE_HASH, HONEST_URI, reason=1, counter=FIXTURE_R + 1)
    resolve(rw, 13, send=True, typed="REJECT 13")
    assert rw["registry"].resolutions[0]["upheld"] is False and rw["registry"].claims[13]["state"] == 3


@pytest.mark.parametrize("typed", ["", "uphold 14", "UPHOLD 1", "REJECT 14", "yes"])
def test_wrong_confirmation_sends_nothing(rw, typed):
    dispute(rw, 14, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    with pytest.raises(Refused, match="confirmation did not match"):
        resolve(rw, 14, send=True, typed=typed)
    assert nothing_sent(rw) and rw["backend"].feed == []


def test_yes_skips_the_prompt_but_still_needs_send(rw):
    dispute(rw, 15, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    (_, sent), prompts = resolve(rw, 15, send=False, yes=True)
    assert sent is None and nothing_sent(rw)
    (_, sent), prompts = resolve(rw, 15, send=True, yes=True)
    assert prompts == [] and sent is not None and len(rw["node"].sent) == 1


def test_unauthorized_signer_is_refused_before_any_fetch(rw):
    dispute(rw, 16, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    rw["node"].set_call(REGISTRY, "resolver()", ["address"], [RESOLVER])  # someone else is the resolver
    with pytest.raises(Refused, match="not the designated resolver"):
        resolve(rw, 16, send=True, yes=True)
    assert nothing_sent(rw) and rw["backend"].requests == []


@pytest.mark.parametrize("party", ["attester", "challenger"])
def test_resolver_that_is_a_party_is_refused(rw, party):
    kwargs = {"attester": TEST_ADDRESS} if party == "attester" else {"challenger": TEST_ADDRESS}
    dispute(rw, 17, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R,
            **kwargs)
    with pytest.raises(Refused, match="ResolverIsParty"):
        resolve(rw, 17, send=True, yes=True)
    assert nothing_sent(rw)


def test_pending_and_missing_claims_are_refused(rw):
    rw["registry"].add(18, FIXTURE_R, FIXTURE_HASH, HONEST_URI, NOW + 100)  # Pending, never challenged
    with pytest.raises(Refused, match="Pending"):
        resolve(rw, 18, send=True, yes=True)
    with pytest.raises(Refused, match="does not exist"):
        resolve(rw, 999, send=True, yes=True)
    assert nothing_sent(rw)


@pytest.mark.parametrize("state, name", [(3, "Finalized"), (4, "Rejected"), (5, "Expired")])
def test_terminal_states_are_nothing_to_do(rw, state, name):
    dispute(rw, 19, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    rw["registry"].set_state(19, state)
    with pytest.raises(NothingToDo, match=f"already {name}"):
        resolve(rw, 19, send=True, yes=True)
    with pytest.raises(NothingToDo):
        cmd_expire(rw["ctx"], 19, True, rw["lines"].append)
    assert nothing_sent(rw)


def test_resolution_deadline_boundary(rw):
    """Contract: resolve needs now < resolutionDeadline. At deadline-1 it is allowed; at the deadline not."""
    dispute(rw, 20, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R,
            resolution_deadline=NOW + 1)
    resolve(rw, 20)  # chain time NOW = deadline - 1: allowed (dry run)
    dispute(rw, 21, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R,
            resolution_deadline=NOW)
    with pytest.raises(Refused, match="resolution window closed"):
        resolve(rw, 21, send=True, yes=True)
    assert nothing_sent(rw)


def test_state_change_between_check_and_send_is_caught_by_the_re_read(rw):
    dispute(rw, 22, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    original = rw["node"].call_handlers[(REGISTRY.lower(), selector("claim(uint256)"))]
    reads = {"n": 0}

    def flip(data):
        reads["n"] += 1
        if reads["n"] > 1:
            rw["registry"].set_state(22, 5)  # expired by someone else meanwhile
        return original(data)

    rw["node"].call_handlers[(REGISTRY.lower(), selector("claim(uint256)"))] = flip
    with pytest.raises(NothingToDo, match="already Expired"):
        resolve(rw, 22, send=True, yes=True)
    assert nothing_sent(rw)


def test_rpc_failure_during_send_then_retry_is_nothing_to_do(rw):
    dispute(rw, 23, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    rw["node"]._eth_getTransactionReceipt = lambda params: None  # the tx lands; the receipt never arrives
    rw["ctx"].client._policy = TxPolicy(receipt_timeout_sec=0.05, receipt_poll_sec=0.01)
    with pytest.raises(ChainError, match="no receipt"):
        resolve(rw, 23, send=True, yes=True)
    assert len(rw["registry"].resolutions) == 1
    with pytest.raises(NothingToDo, match="already Rejected"):  # retrying does not resolve twice
        resolve(rw, 23, send=True, yes=True)
    assert len(rw["registry"].resolutions) == 1


def test_contract_revert_is_decoded(rw):
    dispute(rw, 24, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R)
    rw["node"].revert_estimate_for[selector("resolve(uint256,bool)")] = error_data("ResolutionWindowClosed()")
    with pytest.raises(TransactionReverted, match="ResolutionWindowClosed"):
        resolve(rw, 24, send=True, yes=True)
    assert nothing_sent(rw)


# ------------------------------------------------------------------ expire


def test_expire_respects_the_deadline_boundary(rw):
    """Contract: expireUnresolved needs now >= resolutionDeadline."""
    dispute(rw, 30, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R,
            resolution_deadline=NOW + 1)
    with pytest.raises(Refused, match="still open for 1s"):
        cmd_expire(rw["ctx"], 30, True, rw["lines"].append)
    dispute(rw, 31, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R,
            resolution_deadline=NOW)
    assert cmd_expire(rw["ctx"], 31, False, rw["lines"].append) is None and nothing_sent(rw)  # dry run
    sent = cmd_expire(rw["ctx"], 31, True, rw["lines"].append)
    assert rw["registry"].expiries == [31] and rw["registry"].claims[31]["state"] == 5 and sent is not None
    assert [e["kind"] for e in rw["backend"].feed] == ["EXPIRED"]


def test_expire_refuses_pending_and_needs_a_key(rw, deployment_file):
    rw["registry"].add(32, FIXTURE_R, FIXTURE_HASH, HONEST_URI, NOW + 100)
    with pytest.raises(Refused, match="Pending"):
        cmd_expire(rw["ctx"], 32, True, rw["lines"].append)
    dispute(rw, 33, INFLATED.inflated_usd8, INFLATED.evidence_hash, INFLATED_URI, reason=1, counter=FIXTURE_R,
            resolution_deadline=NOW)
    read_only = ChainClient(Web3(rw["node"]), load_deployment(deployment_file), None)
    ctx = rw["ctx"].__class__(**{**rw["ctx"].__dict__, "client": read_only})
    with pytest.raises(Refused, match="signing key"):
        cmd_expire(ctx, 33, True, rw["lines"].append)
    assert nothing_sent(rw)


# --------------------------------------------------------------------- CLI


def test_cli_defaults_and_errors(tmp_path):
    for name in ("resolve", "expire"):
        params = {p.name: p for p in cli.commands[name].params}
        assert params["dry_run"].default is True
    env = tmp_path / ".env"
    env.write_text(f"DEPLOYMENTS_FILE={tmp_path / 'missing.json'}\n")
    result = CliRunner().invoke(cli, ["show", "1", "--env-file", str(env)])
    assert result.exit_code == 1 and "deployments file not found" in result.output and "Traceback" not in result.output
    assert CliRunner().invoke(cli, ["resolve", "-1"]).exit_code == 2  # negative ids are a usage error
