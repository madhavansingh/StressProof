"""
Malicious attester script for demo and dispute verification.
Matches implementationplan.md §15.4.
"""

import click


@click.command()
@click.option("--dataset", default="weth-stable-fixture-v1", help="Dataset identifier")
@click.option("--shock", default=-3000, type=int, help="Shock in basis points")
def run_malicious(dataset: str, shock: int):
    """Generates an honest case file but posts an inflated 3x claim on-chain."""
    click.echo(f"Malicious attester posting inflated 3x claim for {dataset}...")


def main():
    run_malicious()


if __name__ == "__main__":
    main()
