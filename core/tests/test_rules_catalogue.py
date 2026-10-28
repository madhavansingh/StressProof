"""
Validation catalogue: T-P-33 (one isolated failure per rule V-01..V-14, hostile inputs),
T-P-34 (shuffled accounts never reach replay), T-P-38 (JSON-number amounts rejected before
replay) and the replay-report schema check against docs/schemas/replay-report.md.
"""

import json
import re
from pathlib import Path

import pytest

import stressproof_core.verdict as verdict_module
from stressproof_core import (
    build_replay_report,
    canonical_bytes,
    check_replay_report,
    evaluate,
    keccak256_hex,
    market_id,
    parse_strict,
    validate,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_BYTES = (ROOT / "data" / "fixtures" / "casefile_v1.json").read_bytes()
HONEST_R = 200000000001
MARKET = market_id("aave-v3-eth-weth-stable")


def onchain_for(raw: bytes, claimed: int = HONEST_R) -> dict:
    return {"evidenceHash": keccak256_hex(raw), "marketId": MARKET, "claimedResidualBadDebt": claimed}


def mutated(fn, *, rehash_snapshot: bool = True) -> bytes:
    """Apply fn to a copy of the fixture; keep snapshotHash consistent so only fn's rule can fail."""
    cf = json.loads(FIXTURE_BYTES)
    fn(cf)
    if rehash_snapshot:
        try:
            cf["dataset"]["snapshotHash"] = keccak256_hex(canonical_bytes(cf["snapshot"]))
        except (KeyError, TypeError, ValueError):
            pass
    return canonical_bytes(cf)


def distinct_codes(violations) -> set:
    return {v.code for v in violations}


def _set_path(path, value):
    def fn(cf):
        node = cf
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return fn


# rule -> (raw bytes, onchain)
def _cases():
    cases = {}
    cases["V-01"] = (b"", onchain_for(b""))
    cases["V-02"] = (FIXTURE_BYTES, {**onchain_for(FIXTURE_BYTES), "evidenceHash": "0x" + "ab" * 32})
    spaced = FIXTURE_BYTES.replace(b'"schemaVersion":1', b'"schemaVersion": 1')
    cases["V-03"] = (spaced, onchain_for(spaced))
    raw = mutated(lambda cf: cf["model"].pop("replayerCommit"))
    cases["V-04"] = (raw, onchain_for(raw))
    cases["V-05"] = (FIXTURE_BYTES, {**onchain_for(FIXTURE_BYTES), "marketId": market_id("other")})
    raw = mutated(_set_path(["model", "id"], "static-liquidation-v2"))
    cases["V-06"] = (raw, onchain_for(raw))
    raw = mutated(_set_path(["scenario", "asset"], "WBTC"))
    cases["V-07"] = (raw, onchain_for(raw))
    raw = mutated(_set_path(["scenario", "shockBps"], -9001))
    cases["V-08"] = (raw, onchain_for(raw))
    raw = mutated(_set_path(["snapshot", "assets", "WETH", "priceUsd8"], "0"))
    cases["V-09"] = (raw, onchain_for(raw))
    raw = mutated(lambda cf: cf["snapshot"]["accounts"].reverse())
    cases["V-10"] = (raw, onchain_for(raw))
    raw = mutated(_set_path(["dataset", "counts", "real"], 1))
    cases["V-11"] = (raw, onchain_for(raw))
    raw = mutated(_set_path(["dataset", "dataClass"], "MIXED"))
    cases["V-12"] = (raw, onchain_for(raw))
    raw = mutated(_set_path(["snapshot", "accounts", 0, "debtUsd8", ], "2000000000001"), rehash_snapshot=False)
    cases["V-13"] = (raw, onchain_for(raw))
    cases["V-14"] = (FIXTURE_BYTES, onchain_for(FIXTURE_BYTES, claimed=HONEST_R + 1))
    return cases


CASES = _cases()


@pytest.mark.parametrize("rule", [f"V-{i:02d}" for i in range(1, 15)])
def test_tp33_each_rule_fails_in_isolation(rule):
    raw, onchain = CASES[rule]
    assert distinct_codes(validate(raw, onchain)) == {rule}


@pytest.mark.parametrize("rule", [f"V-{i:02d}" for i in range(1, 14)])
def test_tp33_rules_01_to_13_mean_evidence_invalid(rule):
    raw, onchain = CASES[rule]
    ev = evaluate(raw, onchain)
    assert ev.verdict == "EVIDENCE_INVALID"
    assert ev.counter_residual_usd8 == 0
    assert ev.recomputed is None


def test_tp33_rule_14_means_wrong_result():
    raw, onchain = CASES["V-14"]
    ev = evaluate(raw, onchain)
    assert ev.verdict == "WRONG_RESULT"
    assert ev.counter_residual_usd8 == HONEST_R


def test_tp33_onchain_none_skips_chain_rules():
    for rule in ("V-02", "V-05", "V-14"):
        raw, _ = CASES[rule]
        assert validate(raw, None) == []


HOSTILE = {
    "dataset_is_list": lambda cf: cf.__setitem__("dataset", []),
    "snapshot_is_string": lambda cf: cf.__setitem__("snapshot", "x"),
    "assets_is_list": lambda cf: cf["snapshot"].__setitem__("assets", []),
    "asset_is_null": lambda cf: cf["snapshot"]["assets"].__setitem__("WETH", None),
    "account_is_int": lambda cf: cf["snapshot"]["accounts"].__setitem__(0, 7),
    "missing_account_key": lambda cf: cf["snapshot"]["accounts"][0].pop("origin"),
    "missing_results_key": lambda cf: cf["results"].pop("residualBadDebtUsd8"),
    "allowlist_entry_not_object": lambda cf: cf["dataset"].__setitem__("stablecoinAllowlist", ["USDC"]),
    "ltbps_is_string": lambda cf: cf["snapshot"]["assets"]["WETH"].__setitem__("ltBps", "8300"),
    "id_is_number": lambda cf: cf["snapshot"]["accounts"][0].__setitem__("id", 1),
    "price_is_number": lambda cf: cf["snapshot"]["assets"]["WETH"].__setitem__("priceUsd8", 300000000000),
    "collateral_is_number": lambda cf: cf["snapshot"]["accounts"][0].__setitem__("collateralAmount", 10),
    "results_amount_is_number": lambda cf: cf["results"].__setitem__("debtAtRiskUsd8", 1),
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_tp33_hostile_shapes_never_raise(name):
    raw = mutated(HOSTILE[name])
    violations = validate(raw, onchain_for(raw))
    assert violations, name
    assert evaluate(raw, onchain_for(raw)).verdict == "EVIDENCE_INVALID"


def _forbid_replay(monkeypatch):
    def boom(_):
        raise AssertionError("replay must not run on invalid evidence")
    monkeypatch.setattr(verdict_module, "replay", boom)


def test_tp34_shuffled_accounts_never_reach_replay(monkeypatch):
    raw, onchain = CASES["V-10"]
    _forbid_replay(monkeypatch)
    ev = evaluate(raw, onchain)
    assert ev.verdict == "EVIDENCE_INVALID"
    assert "V-10" in ev.violation_codes


def test_tp38_json_number_amounts_rejected_before_replay(monkeypatch):
    raw = mutated(HOSTILE["collateral_is_number"])
    _forbid_replay(monkeypatch)
    ev = evaluate(raw, onchain_for(raw))
    assert ev.verdict == "EVIDENCE_INVALID"
    assert ev.violation_codes == ["V-09"]


# --- report builder vs docs/schemas/replay-report.md ------------------------------

def _schema_doc_keys() -> set:
    text = (ROOT / "docs" / "schemas" / "replay-report.md").read_text()
    block = re.search(r"```json\n(.*?)\n```", text, re.S).group(1)
    return set(json.loads(block))


def _report(ev, claimed):
    return build_replay_report(
        ev,
        chain_id=31337,
        registry="0x" + "11" * 20,
        claim_id=2**70,
        evidence_hash=keccak256_hex(FIXTURE_BYTES).upper().replace("0X", "0x"),
        fetched_from="http://127.0.0.1:8000/case-files/x",
        watcher="0x" + "22" * 20,
        replayer_commit="abc",
        claimed_onchain_usd8=claimed,
        case_file_copy_uri="http://127.0.0.1:8000/case-files/x",
    )


@pytest.mark.parametrize("claimed", [HONEST_R, 3 * HONEST_R])
def test_report_key_set_matches_schema_doc(claimed):
    ev = evaluate(FIXTURE_BYTES, onchain_for(FIXTURE_BYTES, claimed))
    report = _report(ev, claimed)
    assert set(report) == _schema_doc_keys()
    assert check_replay_report(report) == []


def test_report_round_trips_and_uses_string_ids():
    claimed = 3 * HONEST_R
    report = _report(evaluate(FIXTURE_BYTES, onchain_for(FIXTURE_BYTES, claimed)), claimed)
    raw = canonical_bytes(report)
    assert parse_strict(raw) == report
    assert report["claimId"] == str(2**70)
    assert report["claimedOnChainUsd8"] == str(claimed)
    assert report["evidenceHash"] == keccak256_hex(FIXTURE_BYTES)
