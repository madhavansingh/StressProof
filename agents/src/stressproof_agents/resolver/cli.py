"""Resolver CLI (implementationplan.md §15.3).

    python -m stressproof_agents.resolver.cli show    <claimId>
    python -m stressproof_agents.resolver.cli check   <claimId> [--report-out FILE]
    python -m stressproof_agents.resolver.cli resolve <claimId> [--dry-run | --send] [--yes]
    python -m stressproof_agents.resolver.cli expire  <claimId> [--dry-run | --send]

show and check never send anything. resolve and expire are dry runs unless --send is given;
resolve with --send also asks you to type "UPHOLD <id>" or "REJECT <id>" unless --yes is given.
The decision is the resolver's own: stressproof_core.evaluate() on the first evidence bytes that
match the on-chain hash (C-19). The challenger's counter and report are shown but never decide.
Exit codes: 0 done or nothing to do, 1 refused or failed, 2 usage error.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

import click
from stressproof_core import canonical_bytes

from ..attester.context import read_env
from ..common.chain import ChainClient, ChainError, TransactionReverted
from ..common.config import AgentSettings, ConfigError, load_private_key
from ..common.deployments import Deployment, DeploymentError, load_deployment
from ..common.feed import FeedClient
from ..common.fetch import EvidenceFetcher
from ..watcher.main import replayer_commit
from .actions import ACTOR, NothingToDo, Refused, check_expire_allowed, check_resolve_allowed, send_expire, send_resolve
from .assess import Assessment, assess
from .claim_view import ClaimView, read_claim_view

Echo = Callable[[str], None]


@dataclass(frozen=True)
class ResolverContext:
    settings: AgentSettings
    deployment: Deployment
    client: ChainClient
    fetcher: EvidenceFetcher
    feed: FeedClient
    commit: str


def build_context(env: Mapping[str, str], need_key: bool) -> ResolverContext:
    settings = AgentSettings.from_env(env)
    deployment = load_deployment(settings.deployments_file)
    try:
        key = load_private_key("RESOLVER", env)
    except ConfigError:
        if need_key:
            raise
        key = None  # show/check work read-only
    client = ChainClient.connect(settings.rpc_url_for(deployment.chain_id), deployment, key)
    client.verify_deployment()
    return ResolverContext(settings, deployment, client, EvidenceFetcher(settings.fetch),
                           FeedClient(settings.backend_url, settings.api_write_token), replayer_commit(env))


# ------------------------------------------------------------------ commands


def cmd_show(ctx: ResolverContext, claim_id: int, echo: Echo) -> ClaimView:
    claim = read_claim_view(ctx.client, claim_id)
    now = ctx.client.latest_block_timestamp()
    designated = ctx.client.call(ctx.client.registry.functions.resolver())
    echo(f"claim {claim_id}: {claim.state_name}   (chain time {now})")
    echo(f"  attester            {claim.attester}")
    echo(f"  claimed residual    {claim.claimed_usd8}")
    echo(f"  evidenceHash        {claim.evidence_hash}")
    echo(f"  caseFileURI         {claim.case_file_uri}")
    echo(f"  challenge deadline  {claim.challenge_deadline} ({_relative(claim.challenge_deadline, now)})")
    if claim.challenger != "0x" + "00" * 20:
        echo(f"  challenger          {claim.challenger}")
        echo(f"  reason              {claim.reason_name} ({claim.reason})")
        echo(f"  counter residual    {claim.counter_usd8}")
        echo(f"  replay report       {claim.replay_report_uri} ({claim.replay_report_hash})")
        echo(f"  resolution deadline {claim.resolution_deadline} ({_relative(claim.resolution_deadline, now)})")
    echo(f"  designated resolver {designated}"
         + ("" if ctx.client.address is None else f"   (this signer: {ctx.client.address})"))
    return claim


def cmd_check(ctx: ResolverContext, claim_id: int, echo: Echo, report_out: Optional[Path] = None) -> Assessment:
    claim = read_claim_view(ctx.client, claim_id)
    result = _assess(ctx, claim)
    _print_assessment(result, echo)
    if report_out is not None:
        report_out.write_bytes(canonical_bytes(result.resolver_report))
        echo(f"resolver replay report written to {report_out}")
    return result


def cmd_resolve(ctx: ResolverContext, claim_id: int, send: bool, yes: bool, echo: Echo,
                prompt: Callable[[str], str] = lambda text: click.prompt(text, default="", show_default=False)):
    claim = read_claim_view(ctx.client, claim_id)
    check_resolve_allowed(ctx.client, claim, ctx.client.latest_block_timestamp())
    result = _assess(ctx, claim)
    _print_assessment(result, echo)
    upheld = result.upheld
    if not send:
        echo(f"DRY RUN: would send resolve({claim_id}, {str(upheld).lower()}). Re-run with --send to send it.")
        return result, None
    expected = f"{result.decision} {claim_id}"
    if not yes and prompt(f"Type '{expected}' to confirm").strip() != expected:
        raise Refused("confirmation did not match; nothing sent")
    ctx.feed.post(ACTOR, "RESOLVER_VERDICT", claim_id=claim_id,
                  data={"verdict": result.evaluation.verdict, "upheld": upheld,
                        "violations": result.evaluation.violation_codes})
    sent = send_resolve(ctx.client, claim_id, upheld, ctx.feed)
    echo(f"resolved claim {claim_id} ({result.decision}) in {sent.tx_hash}, block {sent.block_number}: {sent.detail}")
    return result, sent


def cmd_expire(ctx: ResolverContext, claim_id: int, send: bool, echo: Echo):
    claim = read_claim_view(ctx.client, claim_id)
    check_expire_allowed(claim, ctx.client.latest_block_timestamp())
    if not send:
        echo(f"DRY RUN: claim {claim_id} can be expired; would send expireUnresolved({claim_id}). "
             "Re-run with --send to send it.")
        return None
    sent = send_expire(ctx.client, claim_id, ctx.feed)
    echo(f"expired claim {claim_id} in {sent.tx_hash}, block {sent.block_number}: {sent.detail}")
    return sent


# ------------------------------------------------------------------- output


def _assess(ctx: ResolverContext, claim: ClaimView) -> Assessment:
    signer = ctx.client.address or ctx.client.call(ctx.client.registry.functions.resolver())
    return assess(claim, ctx.fetcher, ctx.settings.backend_url, signer, ctx.deployment.chain_id,
                  ctx.deployment.registry, ctx.commit)


def _print_assessment(result: Assessment, echo: Echo) -> None:
    claim, ev = result.claim, result.evaluation
    echo(f"claim {claim.claim_id}: {claim.state_name}, challenged as {claim.reason_name} "
         f"with counter {claim.counter_usd8}")
    for attempt in result.attempts:
        echo(f"  evidence from {attempt.name:<16} {attempt.outcome}   [{attempt.uri}]")
    if result.evidence_source is None:
        echo("  no source returned bytes matching the on-chain evidenceHash: evidence unavailable")
    recomputed = ev.recomputed.residual_bad_debt_usd8 if ev.recomputed is not None else None
    echo(f"  resolver verdict    {ev.verdict}   violations {ev.violation_codes or 'none'}")
    echo(f"  claimed on chain    {claim.claimed_usd8}   in file {ev.claimed_in_file_usd8}   recomputed {recomputed}")
    report = result.report_check
    status = "hash OK" if report.hash_ok else ("hash MISMATCH" if report.available else "unavailable")
    echo(f"  challenger report   {status}" + "".join(f"; {p}" for p in report.problems))
    for diff in report.differences:
        echo(f"    differs: {diff}")
    echo(f"  DECISION            {result.decision} the challenge ({'challenger' if result.upheld else 'attester'} "
         f"wins 2 x BOND)")


def _relative(deadline: int, now: int) -> str:
    return f"{deadline - now}s left" if deadline > now else f"passed {now - deadline}s ago"


# ---------------------------------------------------------------------- CLI


def _run(env_file: Optional[Path], need_key: bool, action: Callable[[ResolverContext], object]) -> None:
    try:
        action(build_context(read_env(env_file), need_key))
    except NothingToDo as exc:
        click.echo(str(exc))
    except Refused as exc:
        click.echo(f"REFUSED: {exc}", err=True)
        sys.exit(1)
    except TransactionReverted as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    except ChainError as exc:
        click.echo(f"ERROR: {exc}. If a transaction was being sent it may have landed; run `show` before retrying.",
                   err=True)
        sys.exit(1)
    except (ConfigError, DeploymentError) as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)


@click.group()
def cli() -> None:
    """StressProof resolver: inspect, check and settle disputed claims."""


ENV_OPTION = click.option("--env-file", type=click.Path(dir_okay=False, path_type=Path), default=None)


@cli.command()
@click.argument("claim_id", type=click.IntRange(min=0))
@ENV_OPTION
def show(claim_id: int, env_file: Optional[Path]) -> None:
    """Print the claim, its challenge and deadlines. Read-only."""
    _run(env_file, False, lambda ctx: cmd_show(ctx, claim_id, click.echo))


@cli.command()
@click.argument("claim_id", type=click.IntRange(min=0))
@click.option("--report-out", type=click.Path(dir_okay=False, path_type=Path), default=None,
              help="Write the resolver's own replay report (canonical JSON) to this file.")
@ENV_OPTION
def check(claim_id: int, report_out: Optional[Path], env_file: Optional[Path]) -> None:
    """Fetch, hash-check and evaluate the evidence; print the verdict. Read-only."""
    _run(env_file, False, lambda ctx: cmd_check(ctx, claim_id, click.echo, report_out))


@cli.command()
@click.argument("claim_id", type=click.IntRange(min=0))
@click.option("--dry-run/--send", "dry_run", default=True, show_default=True)
@click.option("--yes", is_flag=True, help="Skip the typed confirmation (still requires --send).")
@ENV_OPTION
def resolve(claim_id: int, dry_run: bool, yes: bool, env_file: Optional[Path]) -> None:
    """Check the claim, then (with --send) send resolve(id, upheld)."""
    _run(env_file, True, lambda ctx: cmd_resolve(ctx, claim_id, not dry_run, yes, click.echo))


@cli.command()
@click.argument("claim_id", type=click.IntRange(min=0))
@click.option("--dry-run/--send", "dry_run", default=True, show_default=True)
@ENV_OPTION
def expire(claim_id: int, dry_run: bool, env_file: Optional[Path]) -> None:
    """After the resolution deadline, (with --send) send expireUnresolved(id). Anyone may."""
    _run(env_file, True, lambda ctx: cmd_expire(ctx, claim_id, not dry_run, click.echo))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
