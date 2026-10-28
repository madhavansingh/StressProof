"""Honest attester (implementationplan.md §15.1).

    python -m stressproof_agents.attester.main run [--dataset ID] [--shock BPS]
        [--rationale-file FILE] [--dry-run | --send] [--auto-finalize] [--env-file PATH]

1. POST /stress/run builds and stores the case file.
2. The case file is fetched back through the SSRF-safe fetcher and its keccak256 checked.
3. stressproof_core.evaluate() must return MATCH against the claim about to be posted.
4. BOND is read from the chain; postClaim is simulated with eth_call.
5. Only with --send: postClaim is sent, ClaimPosted is parsed and checked, and the feed is told.
   With --auto-finalize it then waits out the challenge window, finalizes, applies to the vault
   and withdraws the bond.

Dry run is the default: nothing is signed or sent unless --send is given.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import click
from stressproof_core import sanitize_rationale
from stressproof_core.constants import MAX_SHOCK_BPS, MIN_SHOCK_BPS, VERDICT_MATCH

from ..common.chain import ChainError
from ..common.config import ConfigError
from ..common.deployments import DeploymentError
from ..common.fetch import FetchError
from .backend import BackendError
from .context import AttesterContext, build_context, read_env
from .finalize import FinalizeOutcome, finalize_apply_withdraw, wait_for_deadline
from .workflow import (AttesterError, ClaimPlan, PostedClaim, fetch_verified, plan_claim, self_check,
                       send_post, simulate_post)

ACTOR = "attester"
DEFAULT_DATASET = "weth-stable-fixture-v1"
DEFAULT_SHOCK_BPS = -3000
FINALIZE_POLL_SEC = 2.0
EXPECTED_ERRORS = (AttesterError, BackendError, ChainError, ConfigError, DeploymentError, FetchError)


@dataclass(frozen=True)
class HonestRun:
    plan: ClaimPlan
    simulated_claim_id: int
    posted: Optional[PostedClaim]
    finalized: Optional[FinalizeOutcome]


def default_rationale(shock_bps: int) -> str:
    return f"Phase 1 fixed scenario: {shock_bps} bps WETH shock."  # plan §8.3


def run_honest(ctx: AttesterContext, dataset_id: str, shock_bps: int, rationale: str, send: bool,
               auto_finalize: bool, echo: Callable[[str], None] = click.echo,
               sleep: Callable[[float], None] = time.sleep) -> HonestRun:
    if not MIN_SHOCK_BPS <= shock_bps <= MAX_SHOCK_BPS:
        raise AttesterError(f"shock {shock_bps} bps is outside [{MIN_SHOCK_BPS}, {MAX_SHOCK_BPS}]")
    run = ctx.backend.stress_run(dataset_id, shock_bps, rationale)
    echo(f"case file built: {run.evidence_hash} ({run.data_class}), residual bad debt {run.residual_bad_debt_usd8}")

    evidence = fetch_verified(ctx.fetcher, run.case_file_uri, run.evidence_hash)
    self_check(evidence, ctx.settings.market_id_string, run.residual_bad_debt_usd8, VERDICT_MATCH)
    echo(f"fetched {len(evidence.raw)} bytes from {evidence.fetched_from}; hash OK; core verdict MATCH")

    plan = plan_claim(ctx.client, evidence, ctx.settings.market_id_string, run.residual_bad_debt_usd8)
    simulated = simulate_post(ctx.client, plan)
    echo(f"postClaim simulation OK from {ctx.client.address}: would become claim {simulated}, bond {plan.bond_wei} wei")
    if not send:
        if auto_finalize:
            echo("--auto-finalize ignored in a dry run")
        echo("DRY RUN: no transaction sent. Re-run with --send to post the claim.")
        return HonestRun(plan, simulated, None, None)

    posted = send_post(ctx.client, plan)
    echo(f"claim {posted.claim_id} posted in {posted.tx_hash} (block {posted.block_number}); "
         f"challenge deadline {posted.challenge_deadline}")
    ctx.feed.post(ACTOR, "CLAIM_POSTED", claim_id=posted.claim_id, tx_hash=posted.tx_hash,
                  data={"evidenceHash": plan.evidence_hash, "claimedUsd8": str(plan.claimed_usd8),
                        "caseFileURI": plan.case_file_uri})
    outcome = None
    if auto_finalize:
        max_wait = ctx.deployment.challenge_window_sec + 120
        wait_for_deadline(ctx.client, posted.challenge_deadline, max_wait, FINALIZE_POLL_SEC, sleep)
        outcome = finalize_apply_withdraw(ctx.client, posted, ctx.feed, ACTOR)
        echo(f"finalized={outcome.finalized} applied={outcome.applied} withdrawn={outcome.withdrawn_wei} wei"
             + "".join(f"\n  note: {n}" for n in outcome.notes))
    return HonestRun(plan, simulated, posted, outcome)


# ---------------------------------------------------------------------- CLI


@click.group()
def cli() -> None:
    """StressProof honest attester."""


@cli.command("run")
@click.option("--dataset", "dataset_id", default=None, help="Dataset id (default: DATASET_ID or the fixture)")
@click.option("--shock", "shock_bps", type=int, default=None, help="WETH shock in bps, e.g. -3000")
@click.option("--rationale-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--dry-run/--send", "dry_run", default=True, show_default=True,
              help="Dry run checks everything and sends nothing. --send posts the claim.")
@click.option("--auto-finalize", is_flag=True, help="After posting, finalize, apply to the vault and withdraw.")
@click.option("--env-file", type=click.Path(dir_okay=False, path_type=Path), default=None)
def run_command(dataset_id, shock_bps, rationale_file, dry_run, auto_finalize, env_file) -> None:
    """Build, verify and (with --send) post an honest claim."""
    try:
        env = read_env(env_file)
        shock = shock_bps if shock_bps is not None else int(env.get("FIXED_SCENARIO_SHOCK_BPS") or DEFAULT_SHOCK_BPS)
        rationale = (sanitize_rationale(rationale_file.read_text(encoding="utf-8")) if rationale_file
                     else default_rationale(shock))
        ctx = build_context(env, "ATTESTER")
        click.echo(f"attester {ctx.client.address} on chain {ctx.deployment.chain_id} "
                   f"({'DRY RUN' if dry_run else 'SENDING'})")
        run_honest(ctx, dataset_id or env.get("DATASET_ID") or DEFAULT_DATASET, shock, rationale,
                   send=not dry_run, auto_finalize=auto_finalize)
    except EXPECTED_ERRORS as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    except ValueError as exc:  # e.g. a non-numeric FIXED_SCENARIO_SHOCK_BPS
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
