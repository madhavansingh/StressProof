"""
Step 3: Deterministic synthetic accounts generator.
Matches implementationplan.md §9.5.
"""

import random
from typing import List


def generate_synthetic_accounts(seed: int, count: int = 20) -> List[dict]:
    """
    Generates synthetic borrower accounts with deterministic seed.
    """
    rng = random.Random(seed)
    accounts = []
    for i in range(1, count + 1):
        collateral_eth = rng.randint(1, 100)
        collateral_wei = collateral_eth * (10 ** 18)
        # Healthy LTV between 40% and 75%
        ltv_bps = rng.randint(4000, 7500)
        collateral_val_usd8 = (collateral_wei * 300000000000) // (10 ** 18)
        debt_usd8 = (collateral_val_usd8 * ltv_bps) // 10000

        accounts.append({
            "id": f"synth-{i:04d}",
            "origin": "synthetic",
            "collateralAmount": str(collateral_wei),
            "debtUsd8": str(debt_usd8),
        })
    return accounts


def main():
    print("Generating synthetic accounts...")


if __name__ == "__main__":
    main()
