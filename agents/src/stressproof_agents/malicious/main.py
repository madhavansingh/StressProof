"""Scripted malicious attester: demo only (implementationplan.md §15.4).

    python -m stressproof_agents.malicious.main [--from-hash HASH | --dataset ID --shock BPS]
        [--dry-run | --send] [--env-file PATH]

1. Get an honest case file: by hash from the backend, or a fresh one from POST /stress/run. It is
   fetched through the SSRF-safe fetcher, hash-checked, and must evaluate to MATCH.
2. Inflate only results.residualBadDebtUsd8 to 3R and re-canonicalize (malicious/inflate.py).
3. Store it with POST /case-files, fetch it back, and check with stressproof_core.evaluate() that
   it is hash-consistent and structurally valid for a 3R claim but fails replay: WRONG_RESULT with
   counter R. That is what the watcher must find.
4. Only with --send, and only on local Anvil (31337) or Base Sepolia (84532): post the 3R claim
   from MALICIOUS_PK.

Dry run is the default.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import click
from stressproof_core.constants import VERDICT_MATCH, VERDICT_WRONG_RESULT

from ..attester.backend import BackendError
from ..attester.context import AttesterContext, build_context, read_env
from ..attester.main import DEFAULT_DATASET, DEFAULT_SHOCK_BPS, default_rationale
from ..attester.workflow import (AttesterError, ClaimPlan, PostedClaim, VerifiedEvidence, fetch_verified,
                                 plan_claim, self_check, send_post, simulate_post)
from ..common.chain import ChainError
from ..common.config import ALLOWED_CHAIN_IDS, ConfigError
from ..common.deployments import DeploymentError
from ..common.fetch import FetchError
from .inflate import InflatedCaseFile, TamperError, inflate_residual

ACTOR = "malicious_attester"
BANNER = "*** DEMO ONLY: scripted malicious attester posting a deliberately wrong claim ***"
EXPECTED_ERRORS = (AttesterError, BackendError, ChainError, ConfigError, DeploymentError, FetchError, TamperError)


@dataclass(frozen=True)
class MaliciousRun:
    inflated: InflatedCaseFile
    plan: ClaimPlan
    simulated_claim_id: int
    posted: Optional[PostedClaim]


def honest_evidence(ctx: AttesterContext, from_hash: Optional[str], dataset_id: str, shock_bps: int,
                    echo: Callable[[str], None]) -> VerifiedEvidence:
    if from_hash:
        uri = f"{ctx.settings.backend_url}/case-files/{from_hash.lower()}"
        evidence = fetch_verified(ctx.fetcher, uri, from_hash)
    else:
        run = ctx.backend.stress_run(dataset_id, shock_bps, default_rationale(shock_bps))
        evidence = fetch_verified(ctx.fetcher, run.case_file_uri, run.evidence_hash)
    echo(f"honest case file {evidence.evidence_hash} fetched and hash-checked")
    return evidence


def check_demo_file(evidence: VerifiedEvidence, inflated: InflatedCaseFile, market_id_string: str) -> None:
    """The tampered file must pass every structural rule for a 3R claim and fail only the replay."""
    evaluation = self_check(evidence, market_id_string, inflated.inflated_usd8, VERDICT_WRONG_RESULT)
    if evaluation.violations:
        raise TamperError(f"tampered file has violations {evaluation.violation_codes}; the demo needs a "
                          "well-formed file whose only problem is the result")
    if evaluation.counter_residual_usd8 != inflated.honest_usd8:
        raise TamperError(f"replay gives {evaluation.counter_residual_usd8}, expected the honest {inflated.honest_usd8}")


def run_malicious(ctx: AttesterContext, from_hash: Optional[str], dataset_id: str, shock_bps: int, send: bool,
                  echo: Callable[[str], None] = click.echo) -> MaliciousRun:
    echo(BANNER)
    if ctx.deployment.chain_id not in ALLOWED_CHAIN_IDS:
        raise ChainError(f"refusing to run on chain {ctx.deployment.chain_id}")
    honest = honest_evidence(ctx, from_hash, dataset_id, shock_bps, echo)
    inflated = inflate_residual(honest.raw)  # also rejects non-canonical input and R = 0
    # The starting file must itself be honest: MATCH for a claim of its own stated value.
    self_check(honest, ctx.settings.market_id_string, inflated.honest_usd8, VERDICT_MATCH)
    echo(f"honest file evaluates MATCH; inflated residual {inflated.honest_usd8} -> {inflated.inflated_usd8}; "
         f"new hash {inflated.evidence_hash}")

    stored = ctx.backend.store_case_file(inflated.raw)
    if stored.evidence_hash != inflated.evidence_hash:
        raise AttesterError(f"backend stored the file as {stored.evidence_hash}, expected {inflated.evidence_hash}")
    evidence = fetch_verified(ctx.fetcher, stored.case_file_uri, inflated.evidence_hash)
    if evidence.raw != inflated.raw:
        raise AttesterError("fetched tampered file differs from the bytes that were stored")
    check_demo_file(evidence, inflated, ctx.settings.market_id_string)
    echo(f"tampered file stored at {stored.case_file_uri}; core verdict for a {inflated.inflated_usd8} claim: "
         f"WRONG_RESULT (counter {inflated.honest_usd8}), no structural violations")

    plan = plan_claim(ctx.client, evidence, ctx.settings.market_id_string, inflated.inflated_usd8)
    simulated = simulate_post(ctx.client, plan)
    echo(f"postClaim simulation OK from {ctx.client.address}: would become claim {simulated}")
    if not send:
        echo("DRY RUN: no transaction sent. Re-run with --send to post the inflated claim.")
        return MaliciousRun(inflated, plan, simulated, None)

    posted = send_post(ctx.client, plan)
    echo(f"inflated claim {posted.claim_id} posted in {posted.tx_hash}; deadline {posted.challenge_deadline}")
    ctx.feed.post(ACTOR, "CLAIM_POSTED", claim_id=posted.claim_id, tx_hash=posted.tx_hash,
                  data={"evidenceHash": plan.evidence_hash, "claimedUsd8": str(plan.claimed_usd8),
                        "honestUsd8": str(inflated.honest_usd8), "demo": True})
    return MaliciousRun(inflated, plan, simulated, posted)


@click.command()
@click.option("--from-hash", default=None, help="Start from this honest case file stored on the backend")
@click.option("--dataset", "dataset_id", default=None)
@click.option("--shock", "shock_bps", type=int, default=None)
@click.option("--dry-run/--send", "dry_run", default=True, show_default=True)
@click.option("--env-file", type=click.Path(dir_okay=False, path_type=Path), default=None)
def cli(from_hash, dataset_id, shock_bps, dry_run, env_file) -> None:
    """Post a claim with an inflated (3x) residual bad debt. Demo only."""
    try:
        env = read_env(env_file)
        shock = shock_bps if shock_bps is not None else int(env.get("FIXED_SCENARIO_SHOCK_BPS") or DEFAULT_SHOCK_BPS)
        ctx = build_context(env, "MALICIOUS")
        click.echo(f"malicious attester {ctx.client.address} on chain {ctx.deployment.chain_id} "
                   f"({'DRY RUN' if dry_run else 'SENDING'})")
        run_malicious(ctx, from_hash, dataset_id or env.get("DATASET_ID") or DEFAULT_DATASET, shock,
                      send=not dry_run)
    except EXPECTED_ERRORS as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    except ValueError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
