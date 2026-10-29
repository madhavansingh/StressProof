"""Watcher agent (implementationplan.md §15.2).

    python -m stressproof_agents.watcher.main [--once] [--dry-run | --send] [--env-file PATH]

Polls ClaimPosted from the deployment block (or WATCHER_START_BLOCK), keeps per-claim state in
DATA_DIR/watcher.sqlite, fetches each case file through the SSRF-safe fetcher, evaluates it with
stressproof_core.evaluate(), and challenges WRONG_RESULT (reason 1) or EVIDENCE_INVALID (reason 2)
with a replay report from stressproof_core.build_replay_report(). It never challenges its own
claims, and re-reads the claim on chain right before every transaction.

Dry run is the default: it ingests and evaluates claims and logs what it would do, but never
stores reports, sends challenges or withdraws. --send enables transactions.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Mapping, Optional

import click

from ..attester.backend import BackendClient, BackendError
from ..attester.context import read_env
from ..common.chain import ChainClient, ChainError
from ..common.config import AgentSettings, ConfigError, load_private_key
from ..common.deployments import DeploymentError, load_deployment
from ..common.feed import FeedClient
from ..common.fetch import EvidenceFetcher
from ..common.state import StateError, WatcherState
from .dry_run import DryRunProcessor
from .poller import Watcher
from .processor import ClaimProcessor

EXPECTED_ERRORS = (BackendError, ChainError, ConfigError, DeploymentError, StateError)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def replayer_commit(env: Mapping[str, str], repo_root: Path = Path(".")) -> str:
    """The commit this watcher runs (for the report's replayerCommit): GIT_COMMIT, else .git/HEAD."""
    value = (env.get("GIT_COMMIT") or "").strip()
    if value:
        if not _SHA_RE.match(value):
            raise ConfigError("GIT_COMMIT must be 40 lowercase hex characters")
        return value
    head = repo_root / ".git" / "HEAD"
    try:
        ref = head.read_text().strip()
        if ref.startswith("ref: "):
            name = ref[5:]
            loose = repo_root / ".git" / name
            if loose.is_file():
                ref = loose.read_text().strip()
            else:
                packed = (repo_root / ".git" / "packed-refs").read_text().splitlines()
                ref = next(line.split()[0] for line in packed if line.endswith(" " + name))
    except (OSError, StopIteration):
        raise ConfigError("cannot determine the current commit; set GIT_COMMIT") from None
    if not _SHA_RE.match(ref):
        raise ConfigError("cannot determine the current commit; set GIT_COMMIT")
    return ref


def build_watcher(env: Mapping[str, str], send: bool) -> Watcher:
    settings = AgentSettings.from_env(env)
    deployment = load_deployment(settings.deployments_file)
    client = ChainClient.connect(settings.rpc_url_for(deployment.chain_id), deployment,
                                 load_private_key("WATCHER", env))
    client.verify_deployment()
    bond = client.call(client.registry.functions.BOND())
    if bond != deployment.bond_wei:
        raise DeploymentError(f"on-chain BOND {bond} differs from the deployments file")
    state = WatcherState(settings.data_dir / ("watcher.sqlite" if send else "watcher-dry-run.sqlite"))
    feed = FeedClient(settings.backend_url, settings.api_write_token) if send else None
    fetcher = EvidenceFetcher(settings.fetch)
    commit = replayer_commit(env)
    if send:
        processor = ClaimProcessor(client, fetcher, BackendClient(settings.backend_url, settings.api_write_token),
                                   state, feed, commit, bond)
    else:
        processor = DryRunProcessor(client, fetcher, state)
    start = settings.watcher_start_block if settings.watcher_start_block is not None else deployment.registry_deploy_block
    return Watcher(client, state, processor, feed, start_block=start)


@click.command()
@click.option("--once", is_flag=True, help="Run a single poll and exit.")
@click.option("--dry-run/--send", "dry_run", default=True, show_default=True,
              help="Dry run evaluates claims and sends nothing. --send stores reports and challenges.")
@click.option("--env-file", type=click.Path(dir_okay=False, path_type=Path), default=None)
def cli(once: bool, dry_run: bool, env_file: Optional[Path]) -> None:
    """Watch StressProof claims and challenge the ones that do not reproduce."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        env = read_env(env_file)
        watcher = build_watcher(env, send=not dry_run)
        click.echo(f"watcher {watcher.client.address} on chain {watcher.client.deployment.chain_id} "
                   f"({'DRY RUN' if dry_run else 'SENDING'})")
        if once:
            result = watcher.poll_once()
            click.echo(f"new claims {list(result.new_claims)}, processed {list(result.processed)}, "
                       f"errors {list(result.errors)}, cursor {result.cursor}")
        else:
            watcher.run_forever(AgentSettings.from_env(env).watcher_poll_sec)
    except EXPECTED_ERRORS as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("watcher stopped")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
