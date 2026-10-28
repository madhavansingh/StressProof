"""
Deterministic liquidation replay model: static-liquidation-v1.
Matches Section 10.2 of implementationplan.md.
"""

from typing import Any, Dict

from .constants import BPS
from .models import AccountOutcome, ReplayResult


def replay(case_file: Dict[str, Any]) -> ReplayResult:
    """
    Pure deterministic liquidation replay.
    No I/O, no clock, no floats, integer floor division only.

    Precondition: validate() returned no V-01..V-13 violations for this case file.
    replay() does not re-check the domain; callers outside verdict.evaluate() must validate first.
    Every returned total and per-account amount is a Python int.
    """
    asset_name = case_file["scenario"]["asset"]
    asset_data = case_file["snapshot"]["assets"][asset_name]

    price = int(asset_data["priceUsd8"])
    dec = int(asset_data["decimals"])
    lt = int(asset_data["ltBps"])
    bonus = int(asset_data["bonusBps"])
    shock = int(case_file["scenario"]["shockBps"])

    # Shocked price: floor division
    shocked_price = price * (BPS + shock) // BPS

    liquidatable_count = 0
    debt_at_risk = 0
    liquidation_volume = 0
    residual_bad_debt = 0
    outcomes = []

    for acc in case_file["snapshot"]["accounts"]:
        collateral_amount = int(acc["collateralAmount"])
        debt_usd8 = int(acc["debtUsd8"])

        # Collateral value at shocked price
        cval = collateral_amount * shocked_price // (10 ** dec)

        # Health factor < 1 liquidation condition
        is_liquidatable = (cval * lt // BPS) < debt_usd8

        if is_liquidatable:
            repaid = min(debt_usd8, cval * BPS // bonus)
            residual = debt_usd8 - repaid

            liquidatable_count += 1
            debt_at_risk += debt_usd8
            liquidation_volume += repaid
            residual_bad_debt += residual
        else:
            repaid = 0
            residual = 0

        outcomes.append(
            AccountOutcome(
                id=acc["id"],
                liquidatable=is_liquidatable,
                repaid_usd8=repaid,
                residual_usd8=residual,
                collateral_value_usd8=cval,
            )
        )

    return ReplayResult(
        liquidatable_accounts=liquidatable_count,
        debt_at_risk_usd8=debt_at_risk,
        liquidation_volume_usd8=liquidation_volume,
        residual_bad_debt_usd8=residual_bad_debt,
        outcomes=outcomes,
    )
