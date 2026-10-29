"""
Tests for verdict.evaluate(), the replay-report builder and hostile-input robustness.
The full T-P catalogue lives in later test modules; these cover the Part 1 behaviour.
"""

import copy
import json
from pathlib import Path

import pytest

from stressproof_core import (
    build_case_file,
    build_replay_report,
    canonical_bytes,
    check_replay_report,
    evaluate,
    keccak256_hex,
    market_id,
    parse_strict,
    validate,
)

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "casefile_v1.json"
HONEST_R = 200000000001
MARKET = market_id("aave-v3-eth-weth-stable")


@pytest.fixture(scope="module")
def fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


def onchain_for(raw: bytes, claimed: int) -> dict:
    return {"evidenceHash": keccak256_hex(raw), "marketId": MARKET, "claimedResidualBadDebt": claimed}


def rebuild(case_file: dict) -> bytes:
    return canonical_bytes(case_file)


def codes(violations) -> list:
    return [v.code for v in violations]


# --- verdicts ----------------------------------------------------------------

def test_fixture_is_fully_valid(fixture_bytes):
    assert validate(fixture_bytes, onchain_for(fixture_bytes, HONEST_R)) == []


def test_honest_claim_matches(fixture_bytes):
    ev = evaluate(fixture_bytes, onchain_for(fixture_bytes, HONEST_R))
    assert ev.verdict == "MATCH"
    assert ev.counter_residual_usd8 == 0
    assert ev.hash_matches is True
    assert ev.recomputed.residual_bad_debt_usd8 == HONEST_R
    assert ev.info_mismatches == []
    assert ev.claimed_in_file_usd8 == str(HONEST_R)


def test_malicious_inflated_file_is_wrong_result(fixture_bytes):
    """Spec §11 malicious attester: same snapshot, results tripled, hash recomputed."""
    cf = json.loads(fixture_bytes)
    cf["results"]["residualBadDebtUsd8"] = str(3 * HONEST_R)
    raw = rebuild(cf)
    ev = evaluate(raw, onchain_for(raw, 3 * HONEST_R))
    assert ev.verdict == "WRONG_RESULT"
    assert ev.counter_residual_usd8 == HONEST_R
    assert ev.violations == []
    assert ev.info_mismatches == []


def test_onchain_value_differs_from_file_is_wrong_result(fixture_bytes):
    ev = evaluate(fixture_bytes, onchain_for(fixture_bytes, 3 * HONEST_R))
    assert ev.verdict == "WRONG_RESULT"
    assert codes(ev.violations) == ["V-14"]
    assert ev.counter_residual_usd8 == HONEST_R


def test_file_lies_but_onchain_claim_is_right_is_evidence_invalid(fixture_bytes):
    cf = json.loads(fixture_bytes)
    cf["results"]["residualBadDebtUsd8"] = "5"
    raw = rebuild(cf)
    ev = evaluate(raw, onchain_for(raw, HONEST_R))
    assert ev.verdict == "EVIDENCE_INVALID"
    assert codes(ev.violations) == ["V-14"]
    assert ev.counter_residual_usd8 == 0


def test_info_mismatch_does_not_change_verdict(fixture_bytes):
    cf = json.loads(fixture_bytes)
    cf["results"]["debtAtRiskUsd8"] = "1"
    raw = rebuild(cf)
    ev = evaluate(raw, onchain_for(raw, HONEST_R))
    assert ev.verdict == "MATCH"
    assert ev.info_mismatches == ["debtAtRiskUsd8"]


def test_hash_mismatch_is_evidence_invalid_without_replay(fixture_bytes):
    onchain = onchain_for(fixture_bytes, HONEST_R)
    onchain["evidenceHash"] = "0x" + "11" * 32
    ev = evaluate(fixture_bytes, onchain)
    assert ev.verdict == "EVIDENCE_INVALID"
    assert codes(ev.violations) == ["V-02"]
    assert ev.recomputed is None
    assert ev.hash_matches is False
    assert ev.claimed_in_file_usd8 is None


def test_wrong_market_is_evidence_invalid(fixture_bytes):
    onchain = onchain_for(fixture_bytes, HONEST_R)
    onchain["marketId"] = market_id("some-other-market")
    ev = evaluate(fixture_bytes, onchain)
    assert ev.verdict == "EVIDENCE_INVALID"
    assert "V-05" in codes(ev.violations)


def test_evaluate_rejects_bad_onchain_argument(fixture_bytes):
    with pytest.raises(ValueError):
        evaluate(fixture_bytes, {"evidenceHash": "0x00"})
    with pytest.raises(ValueError):
        evaluate(fixture_bytes, {**onchain_for(fixture_bytes, 0), "claimedResidualBadDebt": "1"})


# --- hostile input never raises ----------------------------------------------

HOSTILE_PAYLOADS = [
    b"",
    b"\xff\xfe",
    b"null",
    b"[]",
    b"123",
    b'"x"',
    b'{"a":1.5}',
    b'{"a":NaN}',
    b'{"a":1,"a":2}',
    b"\xef\xbb\xbf{}",
    b"{}",
    b'{"a":12345678901234567890}',
    b"[" * 5000 + b"]" * 5000,
]


@pytest.mark.parametrize("raw", HOSTILE_PAYLOADS)
def test_hostile_bytes_never_raise(raw):
    onchain = {"evidenceHash": keccak256_hex(raw), "marketId": MARKET, "claimedResidualBadDebt": 1}
    ev = evaluate(raw, onchain)
    assert ev.verdict == "EVIDENCE_INVALID"
    assert ev.violations


def mutate(fixture_bytes: bytes, fn) -> bytes:
    cf = json.loads(fixture_bytes)
    fn(cf)
    return json.dumps(cf, sort_keys=True, separators=(",", ":")).encode()


STRUCTURAL_MUTATIONS = {
    "model_not_object": (lambda cf: cf.__setitem__("model", []), "V-04"),
    "missing_nested_key": (lambda cf: cf["dataset"].pop("counts"), "V-04"),
    "extra_nested_key": (lambda cf: cf["scenario"].__setitem__("extra", 1), "V-04"),
    "accounts_not_list": (lambda cf: cf["snapshot"].__setitem__("accounts", {}), "V-04"),
    "bool_as_int": (lambda cf: cf["scenario"].__setitem__("shockBps", True), "V-04"),
    "schema_version": (lambda cf: cf.__setitem__("schemaVersion", 2), "V-04"),
    "control_char_rationale": (lambda cf: cf.__setitem__("agentRationale", "a\x00b"), "V-04"),
    "amount_as_number": (lambda cf: cf["snapshot"]["accounts"][0].__setitem__("debtUsd8", 5), "V-09"),
    "leading_zero_amount": (lambda cf: cf["snapshot"]["accounts"][0].__setitem__("debtUsd8", "05"), "V-09"),
    "unknown_model": (lambda cf: cf["model"].__setitem__("id", "other-model"), "V-06"),
    "wrong_asset": (lambda cf: cf["scenario"].__setitem__("asset", "WBTC"), "V-07"),
    "shock_out_of_range": (lambda cf: cf["scenario"].__setitem__("shockBps", 0), "V-08"),
    "lt_times_bonus": (lambda cf: cf["snapshot"]["assets"]["WETH"].__setitem__("ltBps", 9600), "V-08"),
    "unsorted_accounts": (lambda cf: cf["snapshot"]["accounts"].reverse(), "V-10"),
    "unknown_origin": (lambda cf: cf["snapshot"]["accounts"][0].__setitem__("origin", "made_up"), "V-10"),
    "counts": (lambda cf: cf["dataset"]["counts"].__setitem__("synthetic", 7), "V-11"),
    "data_class_label": (lambda cf: cf.__setitem__("dataClass", "REAL"), "V-12"),
}


@pytest.mark.parametrize("name", sorted(STRUCTURAL_MUTATIONS))
def test_structural_mutations(fixture_bytes, name):
    fn, expected_code = STRUCTURAL_MUTATIONS[name]
    raw = mutate(fixture_bytes, fn)
    ev = evaluate(raw, onchain_for(raw, HONEST_R))
    assert ev.verdict == "EVIDENCE_INVALID", name
    assert expected_code in codes(ev.violations), (name, codes(ev.violations))


def test_snapshot_tamper_is_v13(fixture_bytes):
    def bump(cf):
        cf["snapshot"]["accounts"][0]["debtUsd8"] = "2000000000001"
    raw = mutate(fixture_bytes, bump)
    assert "V-13" in codes(validate(raw, onchain_for(raw, HONEST_R)))


# --- builders ------------------------------------------------------------------

def test_build_case_file_reproduces_fixture(fixture_bytes):
    cf = parse_strict(fixture_bytes)
    rebuilt = build_case_file(
        snapshot=cf["snapshot"],
        manifest=cf["dataset"],
        scenario=cf["scenario"],
        rationale=cf["agentRationale"],
        replayer_commit=cf["model"]["replayerCommit"],
        market_id_string=cf["marketId"],
    )
    assert canonical_bytes(rebuilt) == fixture_bytes


def test_build_case_file_sanitizes_rationale(fixture_bytes):
    cf = parse_strict(fixture_bytes)
    rebuilt = build_case_file(cf["snapshot"], cf["dataset"], cf["scenario"], "ok\x07\n" + "x" * 5000, "abc")
    assert rebuilt["agentRationale"].startswith("ok\n")
    assert len(rebuilt["agentRationale"]) == 4000
    assert validate(canonical_bytes(rebuilt)) == []


def test_build_case_file_does_not_alias_inputs(fixture_bytes):
    cf = parse_strict(fixture_bytes)
    snapshot = copy.deepcopy(cf["snapshot"])
    rebuilt = build_case_file(snapshot, cf["dataset"], cf["scenario"], "r", "abc")
    rebuilt["snapshot"]["accounts"].clear()
    assert len(snapshot["accounts"]) == 6


def report_for(ev, raw):
    return build_replay_report(
        ev,
        chain_id=31337,
        registry="0x" + "ab" * 20,
        claim_id=7,
        evidence_hash=keccak256_hex(raw),
        fetched_from="http://127.0.0.1:8000/case-files/x",
        watcher="0x" + "cd" * 20,
        replayer_commit="abc123",
        claimed_onchain_usd8=3 * HONEST_R,
        case_file_copy_uri="http://127.0.0.1:8000/case-files/x",
    )


def test_replay_report_shape_wrong_result(fixture_bytes):
    ev = evaluate(fixture_bytes, onchain_for(fixture_bytes, 3 * HONEST_R))
    report = report_for(ev, fixture_bytes)
    assert check_replay_report(report) == []
    assert report["claimId"] == "7"
    assert report["verdict"] == "WRONG_RESULT"
    assert report["recomputed"]["residualBadDebtUsd8"] == str(HONEST_R)
    assert report["violations"] == ["V-14"]
    parse_strict(canonical_bytes(report))


def test_replay_report_shape_evidence_invalid():
    raw = b"not json"
    ev = evaluate(raw, {"evidenceHash": keccak256_hex(raw), "marketId": MARKET, "claimedResidualBadDebt": 1})
    report = report_for(ev, raw)
    assert check_replay_report(report) == []
    assert report["recomputed"] is None
    assert report["claimedInFileUsd8"] is None
    assert report["violations"] == ["V-03"]


def test_check_replay_report_rejects_bad_shapes():
    assert check_replay_report([]) != []
    assert check_replay_report({"verdict": "MATCH"}) != []


# --- B4: explicit invariant (survives python -O) ----------------------------------

def test_wrong_result_counter_rejects_equal_values():
    from stressproof_core.verdict import VerdictInvariantError, wrong_result_counter
    assert wrong_result_counter(HONEST_R, 3 * HONEST_R) == HONEST_R
    with pytest.raises(VerdictInvariantError):
        wrong_result_counter(HONEST_R, HONEST_R)


def test_verdict_has_no_asserts_and_holds_under_python_O():
    import subprocess
    import sys
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src" / "stressproof_core" / "verdict.py"
    assert "assert " not in src.read_text()
    probe = (
        "assert False\n"  # stripped under -O; reaching the next line proves -O is active
        "from stressproof_core.verdict import VerdictInvariantError, wrong_result_counter\n"
        "try:\n    wrong_result_counter(5, 5)\nexcept VerdictInvariantError:\n    print('raised')\n"
    )
    out = subprocess.run([sys.executable, "-O", "-c", probe], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "raised"
