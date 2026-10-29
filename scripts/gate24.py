"""GATE-24 driver (implementationplan.md §21.5, §24): the Phase 1 flow on local Anvil, checked
against contract reads. Run through scripts/e2e_local.sh, which starts the backend.

Scenarios, all through the real CLIs (attester, malicious, watcher, resolver):
  A. honest claim: watcher MATCH, no challenge; warp past the window; finalize; applyClaim
     reduces max LTV to 50%; a 70% borrow reverts LtvTooHigh(7000, 5000); attester withdraws.
  B. 3R claim: watcher challenges WRONG_RESULT (reason 1) with counter R; report hash matches the
     stored report; resolver checks and upholds; claim Rejected; applyClaim reverts NotFinalized;
     the watcher withdraws 2 x BOND (net +BOND minus gas).
  C. expiry: another 3R claim is challenged, nobody resolves; resolve is refused after the
     deadline; expire refunds both sides; the watcher withdraws BOND.
  D. unsuccessful challenge: a fourth key challenges an honest claim with a wrong counter; the
     resolver rejects the challenge (resolve false); the attester is credited 2 x BOND.

Safety: refuses anything but chain 31337 at http://127.0.0.1:8546; wraps the run in evm_snapshot /
evm_revert so the chain returns to its initial state (unless --keep-state); keeps every artifact in
--work-dir; never prints keys. Exit code 0 only if every check passed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

from eth_account import Account  # noqa: E402
from stressproof_core import build_replay_report, canonical_bytes, evaluate, keccak256_hex, market_id, parse_strict  # noqa: E402
from web3 import Web3  # noqa: E402

from stressproof_agents.attester.backend import BackendClient  # noqa: E402
from stressproof_agents.attester.context import read_env  # noqa: E402
from stressproof_agents.common.chain import ChainClient, TransactionReverted  # noqa: E402
from stressproof_agents.common.config import AgentSettings, Secret, load_private_key  # noqa: E402
from stressproof_agents.common.deployments import load_deployment  # noqa: E402
from stressproof_agents.common.state import WatcherState  # noqa: E402
from stressproof_agents.malicious.inflate import inflate_residual  # noqa: E402

LOCAL_RPC = "http://127.0.0.1:8546"
LOCAL_CHAIN_ID = 31337
FIXTURE_DATASET = "weth-stable-fixture-v1"  # the committed fixture dataset (data/fixtures/datasets/)
ANVIL_MNEMONIC = "test test test test test test test test test test test junk"  # public Anvil test accounts
EXTRA_CHALLENGER_INDEX = 5  # a fourth party, outside the five project roles
PENDING, CHALLENGED, FINALIZED, REJECTED, EXPIRED = 1, 2, 3, 4, 5
ZERO = "0x" + "00" * 20


class GateFailure(RuntimeError):
    pass


class Gate:
    def __init__(self, work_dir: Path) -> None:
        self.work_dir = work_dir
        self.results: List[Tuple[str, str, bool, str]] = []
        self.flow = "preflight"
        self.commands: List[Tuple[str, int, int]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((self.flow, name, bool(ok), detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
        return bool(ok)

    def require(self, name: str, ok: bool, detail: str = "") -> None:
        if not self.check(name, ok, detail):
            raise GateFailure(f"{self.flow}: {name} {detail}")

    @property
    def passed(self) -> bool:
        return all(ok for _, _, ok, _ in self.results)


# ---------------------------------------------------------------------- setup


class World:
    """Clients and expected values for the run."""

    def __init__(self, gate: Gate) -> None:
        self.gate = gate
        self.env = dict(read_env(None))
        self.settings = AgentSettings.from_env(self.env)
        self.deployment = load_deployment(self.settings.deployments_file)
        rpc = self.settings.rpc_url_for(self.deployment.chain_id)
        gate.require("deployments file is for local chain 31337", self.deployment.chain_id == LOCAL_CHAIN_ID)
        gate.require("LOCAL_RPC_URL is http://127.0.0.1:8546", rpc == LOCAL_RPC, "refusing any other endpoint")
        self.reader = ChainClient.connect(rpc, self.deployment)  # read-only
        gate.require("connected node reports chain id 31337", self.reader.w3.eth.chain_id == LOCAL_CHAIN_ID)
        self.reader.verify_deployment()
        gate.check("deployment verified on chain (code, BOND, windows, resolver, MARKET_ID, wiring)", True)
        self.w3 = self.reader.w3
        self.bond = self.deployment.bond_wei
        self.addr = {role: Account.from_key(load_private_key(role, self.env).reveal()).address
                     for role in ("DEPLOYER", "ATTESTER", "MALICIOUS", "WATCHER", "RESOLVER")}
        Account.enable_unaudited_hdwallet_features()
        extra = Account.from_mnemonic(ANVIL_MNEMONIC, account_path=f"m/44'/60'/0'/0/{EXTRA_CHALLENGER_INDEX}")
        self.addr["EXTRA"] = extra.address
        self.extra_key = Secret("0x" + bytes(extra.key).hex(), "E2E_EXTRA_CHALLENGER")
        # R is the fixture dataset's honest residual (Appendix A). The honest case file itself is built
        # by the backend from that dataset, so its bytes and hash are taken from scenario A's claim.
        fixture = (REPO_ROOT / "data" / "fixtures" / "casefile_v1.json").read_bytes()
        self.R = int(parse_strict(fixture)["results"]["residualBadDebtUsd8"])
        self.honest_bytes: bytes = b""
        self.honest_hash = ""
        self.inflated = None  # expected tampered file: inflate_residual(honest_bytes), set in scenario A

    def signer(self, role: str) -> ChainClient:
        key = self.extra_key if role == "EXTRA" else load_private_key(role, self.env)
        return ChainClient(self.w3, self.deployment, key)

    # chain helpers
    def claim(self, claim_id: int):
        return self.reader.call(self.reader.registry.functions.claim(claim_id))

    def credits(self, role: str) -> int:
        return self.reader.call(self.reader.registry.functions.credits(self.addr[role]))

    def count(self) -> int:
        return self.reader.call(self.reader.registry.functions.claimCount())

    def now(self) -> int:
        return self.reader.latest_block_timestamp()

    def warp_to(self, timestamp: int) -> None:
        """evm_increaseTime + evm_mine so the latest block's timestamp is at least `timestamp`."""
        delta = timestamp - self.now()
        if delta > 0:
            self.w3.provider.make_request("evm_increaseTime", [delta])
        self.w3.provider.make_request("evm_mine", [])

    def events(self, contract, name: str, from_block: int, claim_id: Optional[int] = None):
        logs = getattr(contract.events, name)().get_logs(from_block=from_block, to_block="latest")
        return [e for e in logs if claim_id is None or e.args.get("claimId") == claim_id]

    def gas_spent(self, address: str, from_block: int) -> int:
        total = 0
        for number in range(from_block, self.w3.eth.block_number + 1):
            for tx in self.w3.eth.get_block(number, full_transactions=True).transactions:
                if tx["from"] == address:
                    r = self.w3.eth.get_transaction_receipt(tx["hash"])
                    total += r["gasUsed"] * r["effectiveGasPrice"]
        return total

    def reverts_with(self, fn, error: str, args=None) -> bool:
        try:
            self.reader.call(fn)
        except TransactionReverted as exc:
            return exc.error is not None and exc.error.name == error and (args is None or tuple(exc.error.args) == args)
        return False


def run_cli(gate: Gate, label: str, module: str, args: List[str], expect: int = 0) -> str:
    env = {**os.environ, "DATA_DIR": str(gate.work_dir / "agents"), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, "-B", "-m", module, *args], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, timeout=300)
    output = proc.stdout + proc.stderr
    (gate.work_dir / "logs").mkdir(exist_ok=True)
    (gate.work_dir / "logs" / f"{len(gate.commands):02d}-{label}.log").write_text(output)
    gate.commands.append((f"{module} {' '.join(args)}", proc.returncode, expect))
    gate.require(f"`{label}` exits {expect}", proc.returncode == expect, f"exit {proc.returncode}: {output[-400:]}")
    return output


def watcher_poll(gate: Gate, label: str) -> str:
    return run_cli(gate, label, "stressproof_agents.watcher.main", ["--once", "--send"])


def watcher_record(gate: Gate, claim_id: int):
    state = WatcherState(gate.work_dir / "agents" / "watcher.sqlite")
    try:
        return state.get(claim_id)
    finally:
        state.close()


# ---------------------------------------------------------------------- flows


def preflight_vault(gate: Gate, w: World) -> None:
    vault = w.reader.vault.functions
    paused, max_ltv = w.reader.call(vault.borrowPaused()), w.reader.call(vault.maxLtvBps())
    if paused or max_ltv != w.deployment.default_max_ltv_bps:
        w.signer("DEPLOYER").transact(w.reader.vault.functions.resetControls())  # owner-only, local only
    gate.require("vault starts at default controls",
                 not w.reader.call(vault.borrowPaused()) and w.reader.call(vault.maxLtvBps()) == w.deployment.default_max_ltv_bps)


def flow_a_honest(gate: Gate, w: World) -> None:
    gate.flow = "A honest"
    start, first_id = w.w3.eth.block_number, w.count() + 1
    out = run_cli(gate, "attester-send", "stressproof_agents.attester.main", ["run", "--send", "--dataset", FIXTURE_DATASET])
    gate.check("attester printed the posted claim id", f"claim {first_id} posted" in out)
    c = w.claim(first_id)
    gate.require("claim is Pending", c[2] == PENDING)
    (posted,) = w.events(w.reader.registry, "ClaimPosted", start, first_id) or [None]
    gate.require("ClaimPosted emitted", posted is not None)
    gate.check("ClaimPosted attester is the attester role", posted.args.attester == w.addr["ATTESTER"])
    gate.check("ClaimPosted value is R", posted.args.claimedResidualBadDebt == w.R, str(posted.args.claimedResidualBadDebt))
    w.honest_hash = "0x" + bytes(posted.args.evidenceHash).hex()
    w.honest_bytes = urllib.request.urlopen(posted.args.caseFileURI, timeout=10).read()
    gate.require("served evidence hashes to the on-chain evidenceHash", keccak256_hex(w.honest_bytes) == w.honest_hash)
    honest = parse_strict(w.honest_bytes)
    gate.check("evidence was built from the fixture dataset", honest["dataset"]["datasetId"] == FIXTURE_DATASET)
    verdict = evaluate(w.honest_bytes, {"evidenceHash": w.honest_hash, "marketId": w.deployment.market_id,
                                        "claimedResidualBadDebt": w.R}).verdict
    gate.check("core evaluates the honest evidence as MATCH", verdict == "MATCH", verdict)
    w.inflated = inflate_residual(w.honest_bytes)  # expected values only; the CLI does the real tampering

    watcher_nonce = w.w3.eth.get_transaction_count(w.addr["WATCHER"])
    watcher_poll(gate, "watcher-poll-A")
    record = watcher_record(gate, first_id)
    gate.check("watcher recorded MATCH", record is not None and record.state == "MATCH" and record.verdict == "MATCH")
    gate.check("watcher sent no transaction", w.w3.eth.get_transaction_count(w.addr["WATCHER"]) == watcher_nonce)
    gate.check("claim not challenged", w.claim(first_id)[2] == PENDING and w.claim(first_id)[4] == ZERO)

    gate.check("70% borrow succeeds before the claim is applied",
               _borrow_ok(w, 10_000 * 10**8, 7_000 * 10**8))
    w.warp_to(c[1])
    gate.require("chain time reached the challenge deadline", w.now() >= c[1])
    attester = w.signer("ATTESTER")
    credit0 = w.credits("ATTESTER")
    tx = attester.transact(w.reader.registry.functions.finalize(first_id))
    gate.check("finalize receipt status 1", tx.receipt["status"] == 1)
    gate.check("ClaimFinalized emitted", len(attester.parse_events(tx.receipt, "StressRegistry", "ClaimFinalized")) == 1)
    gate.check("claim is Finalized", w.claim(first_id)[2] == FINALIZED)
    gate.check("attester credited BOND", w.credits("ATTESTER") - credit0 == w.bond)

    tx = attester.transact(w.reader.vault.functions.applyClaim(first_id))
    (applied,) = attester.parse_events(tx.receipt, "DemoVault", "ClaimApplied") or [None]
    gate.check("ClaimApplied emitted for R", applied is not None and applied.args.claimId == first_id
               and applied.args.residualBadDebt == w.R)
    v = w.reader.vault.functions
    gate.check("vault max LTV reduced to 5000 bps, not paused",
               w.reader.call(v.maxLtvBps()) == w.deployment.reduced_ltv_bps and not w.reader.call(v.borrowPaused()))
    gate.check("vault lastAppliedClaimId is the honest claim", w.reader.call(v.lastAppliedClaimId()) == first_id)
    gate.check("70% borrow now reverts LtvTooHigh(7000, 5000)",
               w.reverts_with(w.reader.market.functions.borrow(10_000 * 10**8, 7_000 * 10**8), "LtvTooHigh", (7000, 5000)))
    gate.check("40% borrow still succeeds (bounded control, not a pause)", _borrow_ok(w, 10_000 * 10**8, 4_000 * 10**8))

    tx = attester.transact(w.reader.registry.functions.withdraw())
    (withdrawn,) = attester.parse_events(tx.receipt, "StressRegistry", "Withdrawn") or [None]
    gate.check("attester withdrew its bond", withdrawn is not None and withdrawn.args.amount == w.bond
               and w.credits("ATTESTER") == 0)


def flow_b_malicious(gate: Gate, w: World) -> int:
    gate.flow = "B malicious"
    start, claim_id = w.w3.eth.block_number, w.count() + 1
    run_cli(gate, "malicious-send", "stressproof_agents.malicious.main", ["--send", "--dataset", FIXTURE_DATASET])
    (posted,) = w.events(w.reader.registry, "ClaimPosted", start, claim_id) or [None]
    gate.require("inflated ClaimPosted emitted", posted is not None)
    gate.check("ClaimPosted attester is the malicious role", posted.args.attester == w.addr["MALICIOUS"])
    gate.check("ClaimPosted value is 3R", posted.args.claimedResidualBadDebt == 3 * w.R)
    gate.check("evidence is the tampered file", "0x" + bytes(posted.args.evidenceHash).hex() == w.inflated.evidence_hash)

    watcher_balance0, watcher_from = w.w3.eth.get_balance(w.addr["WATCHER"]), w.w3.eth.block_number + 1
    watcher_poll(gate, "watcher-poll-B")
    _assert_wrong_result_challenge(gate, w, claim_id)

    run_cli(gate, "resolver-check-B", "stressproof_agents.resolver.cli", ["check", str(claim_id)])
    out = run_cli(gate, "resolver-expire-too-early", "stressproof_agents.resolver.cli", ["expire", str(claim_id)], expect=1)
    gate.check("expire refused while the resolution window is open", "still open" in out)
    credit_w0, credit_m0 = w.credits("WATCHER"), w.credits("MALICIOUS")
    out = run_cli(gate, "resolver-resolve-B", "stressproof_agents.resolver.cli", ["resolve", str(claim_id), "--send", "--yes"])
    gate.check("resolver decided UPHOLD", "UPHOLD" in out)
    gate.check("claim is Rejected", w.claim(claim_id)[2] == REJECTED)
    (resolved,) = w.events(w.reader.registry, "ClaimResolved", start, claim_id) or [None]
    gate.check("ClaimResolved upheld, winner watcher, 2 x BOND", resolved is not None and resolved.args.challengeUpheld
               and resolved.args.winner == w.addr["WATCHER"] and resolved.args.amountCredited == 2 * w.bond)
    gate.check("watcher credited 2 x BOND", w.credits("WATCHER") - credit_w0 == 2 * w.bond)
    gate.check("malicious attester credited nothing", w.credits("MALICIOUS") == credit_m0 == 0)
    gate.check("applyClaim(rejected) reverts NotFinalized",
               w.reverts_with(w.reader.vault.functions.applyClaim(claim_id), "NotFinalized"))

    watcher_poll(gate, "watcher-poll-B-settle")
    record = watcher_record(gate, claim_id)
    gate.check("watcher recorded WON then WITHDRAWN", record is not None and record.state == "WITHDRAWN")
    withdrawn = [e for e in w.events(w.reader.registry, "Withdrawn", start) if e.args.account == w.addr["WATCHER"]]
    gate.check("Withdrawn(watcher, 2 x BOND) emitted", len(withdrawn) == 1 and withdrawn[0].args.amount == 2 * w.bond)
    gate.check("watcher credit is now 0", w.credits("WATCHER") == 0)
    net = w.w3.eth.get_balance(w.addr["WATCHER"]) - watcher_balance0
    gas = w.gas_spent(w.addr["WATCHER"], watcher_from)
    gate.check("watcher balance changed by exactly +BOND minus gas", net == w.bond - gas, f"net {net}, gas {gas}")
    return claim_id


def _assert_wrong_result_challenge(gate: Gate, w: World, claim_id: int) -> None:
    c = w.claim(claim_id)
    gate.require("claim is Challenged", c[2] == CHALLENGED)
    gate.check("challenger is the watcher", c[4] == w.addr["WATCHER"])
    gate.check("reason code is 1 (WRONG_RESULT)", c[3] == 1)
    gate.check("counter is R, not 3R", c[10] == w.R, str(c[10]))
    report_bytes = urllib.request.urlopen(c[12], timeout=10).read()
    gate.check("report bytes hash to the on-chain replayReportHash", keccak256_hex(report_bytes) == "0x" + bytes(c[8]).hex())
    report = parse_strict(report_bytes)
    gate.check("report verdict WRONG_RESULT, recomputed R, claimed 3R, no violations",
               report["verdict"] == "WRONG_RESULT" and report["recomputed"]["residualBadDebtUsd8"] == str(w.R)
               and report["claimedOnChainUsd8"] == str(3 * w.R) and report["violations"] == [] and len(report) == 17)
    gate.check("report names this claim and evidence",
               report["claimId"] == str(claim_id) and report["evidenceHash"] == "0x" + bytes(c[7]).hex())
    events = w.events(w.reader.registry, "ClaimChallenged", 0, claim_id)
    gate.check("ClaimChallenged event matches the claim", len(events) == 1 and events[0].args.reason == 1
               and events[0].args.counterResidualBadDebt == w.R and events[0].args.challenger == w.addr["WATCHER"])
    record = watcher_record(gate, claim_id)
    gate.check("watcher recorded CHALLENGED with WRONG_RESULT", record is not None and record.state == "CHALLENGED"
               and record.verdict == "WRONG_RESULT")


def flow_c_expiry(gate: Gate, w: World) -> None:
    gate.flow = "C expiry"
    start, claim_id = w.w3.eth.block_number, w.count() + 1
    run_cli(gate, "malicious-send-C", "stressproof_agents.malicious.main", ["--send", "--dataset", FIXTURE_DATASET])
    watcher_poll(gate, "watcher-poll-C")
    _assert_wrong_result_challenge(gate, w, claim_id)
    deadline = w.claim(claim_id)[5]
    w.warp_to(deadline)
    gate.require("chain time reached the resolution deadline", w.now() >= deadline)
    out = run_cli(gate, "resolver-resolve-too-late", "stressproof_agents.resolver.cli", ["resolve", str(claim_id)], expect=1)
    gate.check("resolve refused once the resolution window closed", "window closed" in out)
    credit_m0, credit_w0 = w.credits("MALICIOUS"), w.credits("WATCHER")
    run_cli(gate, "resolver-expire-C", "stressproof_agents.resolver.cli", ["expire", str(claim_id), "--send"])
    gate.check("claim is Expired", w.claim(claim_id)[2] == EXPIRED)
    gate.check("ClaimExpired emitted", len(w.events(w.reader.registry, "ClaimExpired", start, claim_id)) == 1)
    gate.check("both bonds refunded (attester +BOND, challenger +BOND)",
               w.credits("MALICIOUS") - credit_m0 == w.bond and w.credits("WATCHER") - credit_w0 == w.bond)
    watcher_poll(gate, "watcher-poll-C-settle")
    record = watcher_record(gate, claim_id)
    gate.check("watcher recorded REFUNDED then WITHDRAWN", record is not None and record.state == "WITHDRAWN")
    gate.check("watcher withdrew its refunded bond", w.credits("WATCHER") == 0)


def flow_d_unsuccessful(gate: Gate, w: World) -> None:
    gate.flow = "D unsuccessful challenge"
    start, claim_id = w.w3.eth.block_number, w.count() + 1
    run_cli(gate, "attester-send-D", "stressproof_agents.attester.main", ["run", "--send", "--dataset", FIXTURE_DATASET])
    gate.require("honest claim posted", w.claim(claim_id)[2] == PENDING and w.claim(claim_id)[9] == w.R)
    watcher_poll(gate, "watcher-poll-D")
    gate.check("watcher left the honest claim alone", w.claim(claim_id)[2] == PENDING)

    # A well-formed report (the backend checks shape with check_replay_report), built by the core
    # library from the honest evidence; the fourth party challenges anyway with a wrong counter.
    gate.check("scenario D reuses the same honest evidence", "0x" + bytes(w.claim(claim_id)[7]).hex() == w.honest_hash)
    onchain = {"evidenceHash": w.honest_hash, "marketId": market_id(w.deployment.market_id_string),
               "claimedResidualBadDebt": w.R}
    report = build_replay_report(
        evaluate(w.honest_bytes, onchain), chain_id=LOCAL_CHAIN_ID, registry=w.deployment.registry, claim_id=claim_id,
        evidence_hash=w.honest_hash, fetched_from="gate24-scenario-d", watcher=w.addr["EXTRA"],
        replayer_commit="0" * 40, claimed_onchain_usd8=w.R)
    backend = BackendClient(w.settings.backend_url, w.settings.api_write_token)
    stored = backend.store_replay_report(canonical_bytes(report))
    extra = w.signer("EXTRA")
    tx = extra.transact(w.reader.registry.functions.challenge(
        claim_id, 1, w.R + 1, stored.case_file_uri, bytes.fromhex(stored.evidence_hash[2:])), value=w.bond)
    gate.check("wrong challenge accepted on chain", tx.receipt["status"] == 1 and w.claim(claim_id)[2] == CHALLENGED
               and w.claim(claim_id)[4] == w.addr["EXTRA"])

    credit_a0, credit_x0 = w.credits("ATTESTER"), w.credits("EXTRA")
    out = run_cli(gate, "resolver-resolve-D", "stressproof_agents.resolver.cli", ["resolve", str(claim_id), "--send", "--yes"])
    gate.check("resolver decided REJECT from its own replay", "REJECT" in out)
    gate.check("claim is Finalized", w.claim(claim_id)[2] == FINALIZED)
    (resolved,) = w.events(w.reader.registry, "ClaimResolved", start, claim_id) or [None]
    gate.check("ClaimResolved not upheld, winner attester, 2 x BOND",
               resolved is not None and not resolved.args.challengeUpheld and resolved.args.winner == w.addr["ATTESTER"]
               and resolved.args.amountCredited == 2 * w.bond)
    gate.check("ClaimFinalized also emitted (C-24)", len(w.events(w.reader.registry, "ClaimFinalized", start, claim_id)) == 1)
    gate.check("attester credited 2 x BOND, wrong challenger nothing",
               w.credits("ATTESTER") - credit_a0 == 2 * w.bond and w.credits("EXTRA") == credit_x0 == 0)


def _borrow_ok(w: World, collateral: int, amount: int) -> bool:
    try:
        w.reader.call(w.reader.market.functions.borrow(collateral, amount))
        return True
    except TransactionReverted:
        return False


def final_checks(gate: Gate, w: World, honest_ids: Tuple[int, ...]) -> None:
    gate.flow = "global"
    challenged = {e.args.claimId: e.args.challenger for e in w.events(w.reader.registry, "ClaimChallenged", 0)}
    gate.check("the watcher never challenged an honest claim",
               all(challenged.get(i) != w.addr["WATCHER"] for i in honest_ids))
    secrets = [load_private_key(r, w.env).reveal()[2:] for r in ("DEPLOYER", "ATTESTER", "MALICIOUS", "WATCHER", "RESOLVER")]
    logs = "".join(p.read_text() for p in (gate.work_dir / "logs").glob("*.log"))
    gate.check("no private key appears in any CLI output", not any(s in logs for s in secrets))


def main() -> int:
    parser = argparse.ArgumentParser(description="GATE-24 local end-to-end check")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--keep-state", action="store_true", help="do not revert the chain afterwards")
    args = parser.parse_args()
    gate = Gate(args.work_dir)
    snapshot = None
    w = None
    try:
        w = World(gate)
        snapshot = w.w3.provider.make_request("evm_snapshot", [])["result"]
        count0 = w.count()
        preflight_vault(gate, w)
        flow_a_honest(gate, w)
        flow_b_malicious(gate, w)
        flow_c_expiry(gate, w)
        flow_d_unsuccessful(gate, w)
        final_checks(gate, w, honest_ids=(count0 + 1, count0 + 4))
    except GateFailure as exc:
        print(f"STOPPED: {exc}")
    except Exception as exc:  # report, do not mask as a pass
        gate.check(f"unexpected error: {type(exc).__name__}", False, str(exc)[:300])
    finally:
        if w is not None and snapshot is not None and not args.keep_state:
            reverted = w.w3.provider.make_request("evm_revert", [snapshot]).get("result")
            print(f"chain reverted to the starting snapshot: {reverted}")
    summary = {"passed": gate.passed, "checks": len(gate.results),
               "failed": [f"{f}: {n} {d}" for f, n, ok, d in gate.results if not ok],
               "commands": [{"command": c, "exit": e, "expected": x} for c, e, x in gate.commands]}
    (args.work_dir / "gate24-summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nGATE-24 local: {'PASS' if gate.passed else 'FAIL'} ({len(gate.results)} checks, "
          f"{len(summary['failed'])} failed)")
    return 0 if gate.passed else 1


if __name__ == "__main__":
    sys.exit(main())
