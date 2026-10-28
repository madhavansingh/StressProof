"""Honest attester (plan §15.1): dry-run safety, evidence checks, backend failures, posting, finalizing."""

import json

import httpx
import pytest
from click.testing import CliRunner
from stressproof_core import canonical_bytes, keccak256_hex, parse_strict

from stressproof_agents.attester.backend import BackendError
from stressproof_agents.attester.main import cli, run_honest
from stressproof_agents.attester.workflow import AttesterError
from stressproof_agents.common.chain import ChainError, TransactionReverted
from stressproof_agents.common.deployments import load_deployment
from stressproof_agents.common.fetch import FetchError

from attester_fakes import BASE, FIXTURE_BYTES, FIXTURE_HASH, FIXTURE_R, FakeBackend, expect_claim, make_context
from conftest import CORE_MARKET_ID, REGISTRY, TEST_ADDRESS, VAULT, FakeNode, error_data, selector

URI = f"{BASE}/case-files/{FIXTURE_HASH}"
DEADLINE = 1_700_000_000 + 13


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def ctx(node, deployment_file, backend):
    expect_claim(node, 1, FIXTURE_R, FIXTURE_HASH, URI, TEST_ADDRESS, DEADLINE)
    return make_context(node, load_deployment(deployment_file), backend)


def _run(ctx, send=False, auto_finalize=False, shock=-3000, lines=None, sleep=lambda s: None):
    out = lines if lines is not None else []
    return run_honest(ctx, "weth-stable-fixture-v1", shock, "Phase 1 fixed scenario: -3000 bps WETH shock.",
                      send=send, auto_finalize=auto_finalize, echo=out.append, sleep=sleep)


def _nothing_sent(node):
    return node.sent == [] and "eth_sendRawTransaction" not in node.requests


# ------------------------------------------------------------------ dry run


def test_dry_run_is_the_default_and_sends_nothing(ctx, node, backend):
    lines = []
    result = _run(ctx, lines=lines)
    assert _nothing_sent(node)
    assert result.posted is None and result.simulated_claim_id == 1
    assert result.plan.claimed_usd8 == FIXTURE_R and result.plan.bond_wei == 10**16
    assert result.plan.market_id == CORE_MARKET_ID and result.plan.evidence_hash == FIXTURE_HASH
    assert backend.feed == []  # no feed entries for a dry run
    assert any("DRY RUN" in line for line in lines)
    body = json.loads(backend.posted("/stress/run")[0].content)
    assert body == {"datasetId": "weth-stable-fixture-v1", "scenario": {"asset": "WETH", "shockBps": -3000},
                    "agentRationale": "Phase 1 fixed scenario: -3000 bps WETH shock."}


def test_auto_finalize_is_ignored_in_a_dry_run(ctx, node):
    lines = []
    _run(ctx, auto_finalize=True, lines=lines)
    assert _nothing_sent(node) and any("ignored" in line for line in lines)


def test_cli_defaults_to_dry_run():
    params = {p.name: p for p in cli.commands["run"].params}
    assert params["dry_run"].default is True
    assert CliRunner().invoke(cli, ["run", "--help"]).exit_code == 0


def test_cli_reports_config_errors_without_a_traceback(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(f"DEPLOYMENTS_FILE={tmp_path / 'missing.json'}\n")
    result = CliRunner().invoke(cli, ["run", "--env-file", str(env_file)])
    assert result.exit_code == 1 and "ERROR: deployments file not found" in result.output
    assert "Traceback" not in result.output


# ------------------------------------------------------------------ sending


def test_send_posts_the_claim_and_reports_it(ctx, node, backend):
    result = _run(ctx, send=True)
    assert len(node.sent) == 1 and node.sent[0]["value"] == 10**16
    assert result.posted.claim_id == 1 and result.posted.attester == TEST_ADDRESS
    assert result.posted.challenge_deadline == DEADLINE
    (entry,) = backend.feed
    assert entry["actor"] == "attester" and entry["kind"] == "CLAIM_POSTED" and entry["claimId"] == "1"
    assert entry["data"] == {"evidenceHash": FIXTURE_HASH, "claimedUsd8": str(FIXTURE_R), "caseFileURI": URI}


def test_claim_posted_event_must_match_what_was_sent(ctx, node):
    expect_claim(node, 1, FIXTURE_R + 1, FIXTURE_HASH, URI, TEST_ADDRESS, DEADLINE)  # chain reports another value
    with pytest.raises(ChainError, match="ClaimPosted.claimedResidualBadDebt"):
        _run(ctx, send=True)


def test_feed_outage_does_not_block_posting(ctx, node, backend):
    original = backend.__call__

    def no_feed(request):
        if request.url.path == "/feed":
            raise httpx.ConnectError("feed down")
        return original(request)

    ctx = ctx.__class__(**{**ctx.__dict__, "feed": ctx.feed.__class__(
        BASE, ctx.settings.api_write_token, transport=httpx.MockTransport(no_feed))})
    assert _run(ctx, send=True).posted.claim_id == 1


# ------------------------------------------------------- evidence checking


def test_fetched_bytes_must_match_the_evidence_hash(ctx, node, backend):
    backend.serve_override[FIXTURE_HASH] = FIXTURE_BYTES.replace(b"WETH", b"WETX", 1)
    with pytest.raises(AttesterError, match="hashes to"):
        _run(ctx, send=True)
    assert _nothing_sent(node)


def test_malformed_evidence_is_refused(ctx, node, backend):
    junk = b'{"not": "a case file"}'
    junk_hash = keccak256_hex(junk)
    backend.store[junk_hash] = junk
    backend.stress_override = lambda r: httpx.Response(200, json={
        "evidenceHash": junk_hash, "caseFileURI": f"{BASE}/case-files/{junk_hash}",
        "results": parse_strict(FIXTURE_BYTES)["results"], "dataClass": "SYNTHETIC"})
    with pytest.raises(AttesterError, match="EVIDENCE_INVALID"):
        _run(ctx, send=True)
    assert _nothing_sent(node)


def test_backend_result_that_disagrees_with_the_file_is_refused(ctx, node, backend):
    results = dict(parse_strict(FIXTURE_BYTES)["results"], residualBadDebtUsd8=str(FIXTURE_R * 2))
    backend.stress_override = lambda r: httpx.Response(200, json={
        "evidenceHash": FIXTURE_HASH, "caseFileURI": URI, "results": results, "dataClass": "SYNTHETIC"})
    with pytest.raises(AttesterError, match="WRONG_RESULT"):
        _run(ctx, send=True)
    assert _nothing_sent(node)


def test_ssrf_case_file_uri_from_backend_is_refused(ctx, node, backend):
    backend.stress_override = lambda r: httpx.Response(200, json={
        "evidenceHash": FIXTURE_HASH, "caseFileURI": "http://169.254.169.254/latest/meta-data/",
        "results": parse_strict(FIXTURE_BYTES)["results"], "dataClass": "SYNTHETIC"})
    with pytest.raises(FetchError):
        _run(ctx, send=True)
    assert _nothing_sent(node)


def test_non_canonical_evidence_is_refused(ctx, node, backend):
    pretty = json.dumps(parse_strict(FIXTURE_BYTES), indent=2).encode()
    h = keccak256_hex(pretty)
    backend.store[h] = pretty
    backend.stress_override = lambda r: httpx.Response(200, json={
        "evidenceHash": h, "caseFileURI": f"{BASE}/case-files/{h}",
        "results": parse_strict(FIXTURE_BYTES)["results"], "dataClass": "SYNTHETIC"})
    with pytest.raises(AttesterError, match="EVIDENCE_INVALID"):
        _run(ctx, send=True)
    assert canonical_bytes(parse_strict(FIXTURE_BYTES)) == FIXTURE_BYTES  # the honest fixture is canonical


# --------------------------------------------------------- backend failures


@pytest.mark.parametrize("response, message", [
    (lambda r: httpx.Response(500, text="boom"), "HTTP 500"),
    (lambda r: httpx.Response(422, json={"detail": "bad scenario"}), "HTTP 422"),
    (lambda r: httpx.Response(200, content=b"not json"), "invalid JSON"),
    (lambda r: httpx.Response(200, json=[]), "expected an object"),
    (lambda r: httpx.Response(200, json={"caseFileURI": URI, "results": {}}), "invalid evidenceHash"),
    (lambda r: httpx.Response(200, json={"evidenceHash": FIXTURE_HASH, "caseFileURI": URI,
                                         "results": {"residualBadDebtUsd8": "1"}}), "unexpected results"),
    (lambda r: httpx.Response(200, json={"evidenceHash": FIXTURE_HASH, "caseFileURI": "",
                                         "results": parse_strict(FIXTURE_BYTES)["results"]}), "invalid caseFileURI"),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")), "unreachable"),
])
def test_backend_failures_stop_before_signing(ctx, node, backend, response, message):
    backend.stress_override = response
    with pytest.raises(BackendError, match=message):
        _run(ctx, send=True)
    assert _nothing_sent(node)


def test_wrong_token_is_reported(ctx, node, backend):
    ctx.backend._token = ctx.backend._token.__class__("wrong", "API_WRITE_TOKEN")
    with pytest.raises(BackendError, match="HTTP 401"):
        _run(ctx, send=True)


@pytest.mark.parametrize("shock", [0, 1, -9001])
def test_shock_outside_the_model_domain_is_refused_before_any_call(ctx, backend, shock):
    with pytest.raises(AttesterError, match="outside"):
        _run(ctx, shock=shock)
    assert backend.requests == []


# ------------------------------------------------------------ chain checks


def test_on_chain_bond_must_match_the_deployment(ctx, node):
    node.set_call(REGISTRY, "BOND()", ["uint256"], [10**15])
    with pytest.raises(AttesterError, match="on-chain BOND"):
        _run(ctx)


def test_simulation_revert_is_decoded_and_nothing_is_sent(ctx, node):
    node.calls[(REGISTRY.lower(), selector("postClaim(bytes32,uint256,bytes32,string)"))] = (
        "revert:" + error_data("BadURI()"))
    with pytest.raises(TransactionReverted) as exc:
        _run(ctx, send=True)
    assert exc.value.error.name == "BadURI" and _nothing_sent(node)


# ----------------------------------------------------------- auto-finalize


def _finalizable(node, credit=10**16):
    node.set_call(REGISTRY, "status(uint256)", ["uint8"], [1])
    node.set_call(REGISTRY, "credits(address)", ["uint256"], [credit])


def _advance(node):
    def sleep(_seconds):
        node.block_number += 1
    return sleep


def test_auto_finalize_finalizes_applies_and_withdraws(ctx, node, backend):
    _finalizable(node)
    result = _run(ctx, send=True, auto_finalize=True, sleep=_advance(node))
    assert result.finalized.finalized and result.finalized.applied and result.finalized.withdrawn_wei == 10**16
    sent_to = [("0x" + bytes(tx["to"]).hex()).lower() for tx in node.sent]
    assert sent_to == [REGISTRY.lower(), REGISTRY.lower(), VAULT.lower(), REGISTRY.lower()]  # post, finalize, apply, withdraw
    assert [e["kind"] for e in backend.feed] == ["CLAIM_POSTED", "FINALIZED", "VAULT_APPLIED", "WITHDRAWN"]


def test_below_threshold_is_noted_and_the_bond_is_still_withdrawn(ctx, node):
    _finalizable(node)
    node.revert_estimate_for[selector("applyClaim(uint256)")] = error_data("BelowThreshold()")
    result = _run(ctx, send=True, auto_finalize=True, sleep=_advance(node))
    assert result.finalized.applied is False and result.finalized.withdrawn_wei == 10**16
    assert any("BelowThreshold" in n for n in result.finalized.notes)


def test_challenged_claim_is_not_applied(ctx, node):
    node.set_call(REGISTRY, "status(uint256)", ["uint8"], [2])  # Challenged
    node.set_call(REGISTRY, "credits(address)", ["uint256"], [0])
    result = _run(ctx, send=True, auto_finalize=True, sleep=_advance(node))
    assert result.finalized.finalized is False and result.finalized.applied is False
    assert len(node.sent) == 1  # only the postClaim


def test_unexpected_vault_revert_is_raised(ctx, node):
    _finalizable(node)
    node.revert_estimate_for[selector("applyClaim(uint256)")] = error_data("WrongMarket()")
    with pytest.raises(TransactionReverted, match="WrongMarket"):
        _run(ctx, send=True, auto_finalize=True, sleep=_advance(node))


def test_stalled_chain_is_reported(ctx, node):
    _finalizable(node)
    with pytest.raises(ChainError, match="not producing blocks"):
        _run(ctx, send=True, auto_finalize=True, sleep=lambda s: None)  # time never advances
