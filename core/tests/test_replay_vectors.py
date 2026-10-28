"""
Replay vectors: T-P-30 (Appendix A, every account), monotonicity table, T-P-36, T-P-37, T-P-38.
"""

import itertools

import pytest

from stressproof_core import BPS, replay

PRICE = "300000000000"
LT = 8300
BONUS = 10500

# (collateralAmount, debtUsd8) -> expected (collateralValue, liquidatable, repaid, residual) at -3000 bps
APPENDIX_A = [
    ("10000000000000000000", "2000000000000", (2100000000000, True, 2000000000000, 0)),
    ("5000000000000000000", "1200000000000", (1050000000000, True, 1000000000000, 200000000000)),
    ("10000000000000000000", "1000000000000", (2100000000000, False, 0, 0)),
    ("1000000000000000000", "174300000000", (210000000000, False, 0, 0)),
    ("1000000000000000000", "174300000001", (210000000000, True, 174300000001, 0)),
    ("1", "1", (0, True, 0, 1)),
]


def case(accounts, shock=-3000, price=PRICE, lt=LT, bonus=BONUS):
    return {
        "scenario": {"asset": "WETH", "shockBps": shock},
        "snapshot": {
            "assets": {"WETH": {"bonusBps": bonus, "decimals": 18, "ltBps": lt, "priceUsd8": price}},
            "accounts": [
                {"id": f"synth-{i:04d}", "origin": "synthetic", "collateralAmount": c, "debtUsd8": d}
                for i, (c, d) in enumerate(accounts, start=1)
            ],
        },
    }


def appendix_a(shock=-3000):
    return case([(c, d) for c, d, _ in APPENDIX_A], shock=shock)


# --- T-P-30 ----------------------------------------------------------------------

def test_tp30_appendix_a_totals():
    r = replay(appendix_a())
    assert r.to_results_dict() == {
        "debtAtRiskUsd8": "3374300000002",
        "liquidatableAccounts": 4,
        "liquidationVolumeUsd8": "3174300000001",
        "residualBadDebtUsd8": "200000000001",
    }


@pytest.mark.parametrize("index", range(len(APPENDIX_A)))
def test_tp30_appendix_a_every_account(index):
    outcome = replay(appendix_a()).outcomes[index]
    cval, liquidatable, repaid, residual = APPENDIX_A[index][2]
    assert outcome.id == f"synth-{index + 1:04d}"
    assert outcome.collateral_value_usd8 == cval
    assert outcome.liquidatable is liquidatable
    assert outcome.repaid_usd8 == repaid
    assert outcome.residual_usd8 == residual


def test_tp30_outcomes_follow_file_order():
    r = replay(appendix_a())
    assert [o.id for o in r.outcomes] == [f"synth-{i:04d}" for i in range(1, 7)]


@pytest.mark.parametrize(
    "shock,liquidatable,residual",
    [(-1000, 2, 1), (-2000, 3, 57142857144), (-3000, 4, 200000000001), (-5000, 5, 1120028571432)],
)
def test_appendix_a_monotonicity_table(shock, liquidatable, residual):
    r = replay(appendix_a(shock))
    assert (r.liquidatable_accounts, r.residual_bad_debt_usd8) == (liquidatable, residual)


# --- T-P-36 ----------------------------------------------------------------------

CVALS = [0, 1, 9999, 10000, 210000000000, 2100000000001, 10**20 + 3]
LTS = [1, 5000, 8300, 9999]


@pytest.mark.parametrize("cval,lt", list(itertools.product(CVALS, LTS)))
def test_tp36_floor_form_equals_cross_multiplied_form(cval, lt):
    q = cval * lt // BPS
    for debt in (q - 1, q, q + 1):
        if debt < 0:
            continue
        assert ((cval * lt // BPS) < debt) == (cval * lt < debt * BPS), (cval, lt, debt)


def test_tp36_both_divisible_and_non_divisible_products_are_exercised():
    products = [c * lt for c, lt in itertools.product(CVALS, LTS) if c]
    assert any(p % BPS == 0 for p in products)
    assert any(p % BPS != 0 for p in products)


def test_tp36_replay_boundary_accounts():
    """Appendix A …0004 sits exactly on the threshold (not liquidatable); …0005 is one unit over."""
    r = replay(appendix_a())
    assert r.outcomes[3].liquidatable is False
    assert r.outcomes[4].liquidatable is True


# --- T-P-37 ----------------------------------------------------------------------

def test_tp37_exact_above_2_pow_53():
    collateral = 10**24 + 1
    debt = 2**60 + 7
    r = replay(case([(str(collateral), str(debt))]))
    o = r.outcomes[0]
    assert o.collateral_value_usd8 == 210000000000000000          # (10**24+1) * 2.1e11 // 1e18
    assert o.liquidatable is True
    assert o.repaid_usd8 == 200000000000000000                    # cval * 10000 // 10500
    assert o.residual_usd8 == 952921504606846983                  # 2**60 + 7 - 2e17
    assert r.residual_bad_debt_usd8 == 952921504606846983
    assert int(float(o.residual_usd8)) != o.residual_usd8
    assert int(float(debt)) != debt


def test_tp37_non_round_collateral_value_is_exact():
    """cval here is ~1.9e20 and not a multiple of a power of two, so any float step changes it."""
    collateral = 10**27 + 123456789
    shocked = 285714285714 * (BPS - 3333) // BPS           # 190485714285
    expected_cval = collateral * shocked // 10**18           # 190485714285000000023
    assert expected_cval == 190485714285000000023
    debt = 2**68 + 7                                         # 295147905179352825863
    r = replay(case([(str(collateral), str(debt))], shock=-3333, price="285714285714"))
    o = r.outcomes[0]
    assert o.collateral_value_usd8 == expected_cval
    assert o.liquidatable is True
    assert o.repaid_usd8 == expected_cval * BPS // BONUS     # 181414965985714285736
    assert o.repaid_usd8 == 181414965985714285736
    assert o.residual_usd8 == debt - 181414965985714285736
    assert int(float(collateral) * shocked / 1e18) != expected_cval


def test_tp37_sub_unit_collateral_floors_to_zero_not_rounds():
    # 10**24 + 1 wei times a price with a remainder: the extra wei must floor away exactly.
    r = replay(case([(str(10**24 + 1), "1")], shock=-1, price="99999999999"))
    shocked = 99999999999 * (BPS - 1) // BPS
    assert r.outcomes[0].collateral_value_usd8 == (10**24 + 1) * shocked // 10**18


# --- T-P-38 ----------------------------------------------------------------------

def test_tp38_every_number_is_a_plain_int():
    r = replay(appendix_a())
    for value in (r.liquidatable_accounts, r.debt_at_risk_usd8, r.liquidation_volume_usd8, r.residual_bad_debt_usd8):
        assert type(value) is int
    for o in r.outcomes:
        assert type(o.liquidatable) is bool
        for value in (o.repaid_usd8, o.residual_usd8, o.collateral_value_usd8):
            assert type(value) is int


def test_tp38_serialized_amounts_are_decimal_strings():
    results = replay(appendix_a()).to_results_dict()
    assert type(results["liquidatableAccounts"]) is int
    for key in ("debtAtRiskUsd8", "liquidationVolumeUsd8", "residualBadDebtUsd8"):
        assert isinstance(results[key], str) and results[key].isdigit()
    for o in replay(appendix_a()).outcomes:
        d = o.to_dict()
        assert all(isinstance(d[k], str) for k in ("repaidUsd8", "residualUsd8", "collateralValueUsd8"))
