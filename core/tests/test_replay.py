"""
Tests for replay model static-liquidation-v1 against Appendix A test vectors.
"""

from stressproof_core.replay import replay


def test_replay_appendix_a_vectors():
    case_file = {
        "scenario": {
            "asset": "WETH",
            "shockBps": -3000,
        },
        "snapshot": {
            "assets": {
                "WETH": {
                    "decimals": 18,
                    "priceUsd8": "300000000000",
                    "ltBps": 8300,
                    "bonusBps": 10500,
                }
            },
            "accounts": [
                {
                    "id": "0x0000000000000000000000000000000000000001",
                    "collateralAmount": "10000000000000000000",
                    "debtUsd8": "2000000000000",
                    "origin": "real_aave_v3_fork",
                },
                {
                    "id": "0x0000000000000000000000000000000000000002",
                    "collateralAmount": "5000000000000000000",
                    "debtUsd8": "1200000000000",
                    "origin": "real_aave_v3_fork",
                },
                {
                    "id": "0x0000000000000000000000000000000000000003",
                    "collateralAmount": "10000000000000000000",
                    "debtUsd8": "1000000000000",
                    "origin": "real_aave_v3_fork",
                },
                {
                    "id": "0x0000000000000000000000000000000000000004",
                    "collateralAmount": "1000000000000000000",
                    "debtUsd8": "174300000000",
                    "origin": "real_aave_v3_fork",
                },
                {
                    "id": "0x0000000000000000000000000000000000000005",
                    "collateralAmount": "1000000000000000000",
                    "debtUsd8": "174300000001",
                    "origin": "real_aave_v3_fork",
                },
                {
                    "id": "0x0000000000000000000000000000000000000006",
                    "collateralAmount": "1",
                    "debtUsd8": "1",
                    "origin": "real_aave_v3_fork",
                },
            ],
        },
    }

    result = replay(case_file)

    assert result.liquidatable_accounts == 4
    assert result.debt_at_risk_usd8 == 3374300000002
    assert result.liquidation_volume_usd8 == 3174300000001
    assert result.residual_bad_debt_usd8 == 200000000001

    # Invariant: debtAtRisk == volume + residual
    assert result.debt_at_risk_usd8 == result.liquidation_volume_usd8 + result.residual_bad_debt_usd8

    # Account 4 boundary condition: equality -> not liquidatable
    acc4 = [o for o in result.outcomes if o.id.endswith("0004")][0]
    assert not acc4.liquidatable
    assert acc4.repaid_usd8 == 0
    assert acc4.residual_usd8 == 0

    # Account 5 boundary condition: 1 unit above -> liquidatable
    acc5 = [o for o in result.outcomes if o.id.endswith("0005")][0]
    assert acc5.liquidatable
    assert acc5.repaid_usd8 == 174300000001
    assert acc5.residual_usd8 == 0
