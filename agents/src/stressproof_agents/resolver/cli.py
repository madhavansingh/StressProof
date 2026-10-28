"""
Resolver CLI for dispute adjudication.
Matches implementationplan.md §15.3.
"""

import click


@click.group()
def cli():
    """StressProof Resolver CLI."""
    pass


@cli.command()
@click.argument("claim_id", type=int)
def show(claim_id: int):
    """Print claim details, challenge status, and deadlines."""
    click.echo(f"Showing claim {claim_id}...")


@cli.command()
@click.argument("claim_id", type=int)
def check(claim_id: int):
    """Fetch, validate, and replay claim to print verdict without sending tx."""
    click.echo(f"Checking claim {claim_id}...")


@cli.command()
@click.argument("claim_id", type=int)
@click.option("--yes", is_flag=True, help="Skip interactive confirmation")
def resolve(claim_id: int, yes: bool):
    """Resolve a dispute after independent verification."""
    click.echo(f"Resolving claim {claim_id} (auto-confirm: {yes})...")


@cli.command()
@click.argument("claim_id", type=int)
def expire(claim_id: int):
    """Expire unresolved claim after resolution window elapses."""
    click.echo(f"Expiring claim {claim_id}...")


def main():
    cli()


if __name__ == "__main__":
    main()
