"""
Replay properties: T-P-31, T-P-32 and the exact Fraction reference oracle T-P-35.
"""

from fractions import Fraction

from hypothesis import given, settings
from hypothesis import strategies as st

from stressproof_core import BPS, replay

_APPENDIX_A = [
    ("10000000000000000000", "2000000000000"),
    ("5000000000000000000", "1200000000000"),
    ("10000000000000000000", "1000000000000"),
    ("1000000000000000000", "174300000000"),
    ("1000000000000000000", "174300000001"),
    ("1", "1"),
]


def appendix_a_case(shock):
    return {
        "scenario": {"asset": "WETH", "shockBps": shock},
        "snapshot": {
            "assets": {"WETH": {"bonusBps": 10500, "decimals": 18, "ltBps": 8300, "priceUsd8": "300000000000"}},
            "accounts": [
                {"id": f"synth-{i:04d}", "origin": "synthetic", "collateralAmount": c, "debtUsd8": d}
                for i, (c, d) in enumerate(_APPENDIX_A, start=1)
            ],
        },
    }


def oracle(case_file):
    """
    Deliberately naive second implementation using exact rationals.
    Floors are taken with // on Fractions; the liquidation test compares the unfloored rational.
    """
    asset = case_file["snapshot"]["assets"][case_file["scenario"]["asset"]]
    price = Fraction(int(asset["priceUsd8"]))
    lt = Fraction(asset["ltBps"])
    bonus = Fraction(asset["bonusBps"])
    shock = Fraction(case_file["scenario"]["shockBps"])
    unit = Fraction(10) ** asset["decimals"]

    shocked = (price * (BPS + shock) / BPS) // 1
    totals = [0, 0, 0, 0]
    outcomes = []
    for acc in case_file["snapshot"]["accounts"]:
        coll = Fraction(int(acc["collateralAmount"]))
        debt = Fraction(int(acc["debtUsd8"]))
        cval = (coll * shocked / unit) // 1
        liquidatable = cval * lt / BPS < debt
        if liquidatable:
            repaid = min(debt, (cval * BPS / bonus) // 1)
            residual = debt - repaid
            totals[0] += 1
            totals[1] += debt
            totals[2] += repaid
            totals[3] += residual
        else:
            repaid = residual = Fraction(0)
        outcomes.append((acc["id"], liquidatable, int(repaid), int(residual), int(cval)))
    return tuple(int(t) for t in totals), outcomes


def actual(case_file):
    r = replay(case_file)
    totals = (r.liquidatable_accounts, r.debt_at_risk_usd8, r.liquidation_volume_usd8, r.residual_bad_debt_usd8)
    outcomes = [(o.id, o.liquidatable, o.repaid_usd8, o.residual_usd8, o.collateral_value_usd8) for o in r.outcomes]
    return totals, outcomes


accounts_st = st.lists(
    st.tuples(st.integers(1, 10**27), st.integers(0, 10**20)),
    min_size=0,
    max_size=12,
)


@st.composite
def case_files(draw, shock=None):
    accounts = draw(accounts_st)
    return {
        "scenario": {"asset": "WETH", "shockBps": draw(st.integers(-9000, -1)) if shock is None else shock},
        "snapshot": {
            "assets": {
                "WETH": {
                    "bonusBps": draw(st.integers(10001, 15000)),
                    "decimals": 18,
                    "ltBps": draw(st.integers(1, 9999)),
                    "priceUsd8": str(draw(st.integers(1, 10**14))),
                }
            },
            "accounts": [
                {"id": f"synth-{i:04d}", "origin": "synthetic", "collateralAmount": str(c), "debtUsd8": str(d)}
                for i, (c, d) in enumerate(accounts, start=1)
            ],
        },
    }


# --- T-P-35 ----------------------------------------------------------------------

def test_tp35_oracle_matches_on_appendix_a():
    for shock in (-1000, -2000, -3000, -5000, -9000, -1):
        cf = appendix_a_case(shock)
        assert actual(cf) == oracle(cf)


@settings(max_examples=200, deadline=None)
@given(case_files())
def test_tp35_oracle_matches_on_generated_snapshots(cf):
    assert actual(cf) == oracle(cf)


# --- T-P-31 ----------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(case_files())
def test_tp31_accounting_identities(cf):
    r = replay(cf)
    assert 0 <= r.residual_bad_debt_usd8 <= r.debt_at_risk_usd8
    assert r.liquidation_volume_usd8 + r.residual_bad_debt_usd8 == r.debt_at_risk_usd8
    assert 0 <= r.liquidatable_accounts <= len(cf["snapshot"]["accounts"])
    assert r.liquidatable_accounts == sum(o.liquidatable for o in r.outcomes)


# --- T-P-32 ----------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(case_files(shock=-1), st.integers(-9000, -1), st.integers(-9000, -1))
def test_tp32_deeper_shock_never_decreases_risk(cf, s1, s2):
    shallow, deep = max(s1, s2), min(s1, s2)
    cf_shallow = {**cf, "scenario": {"asset": "WETH", "shockBps": shallow}}
    cf_deep = {**cf, "scenario": {"asset": "WETH", "shockBps": deep}}
    a, b = replay(cf_shallow), replay(cf_deep)
    assert b.liquidatable_accounts >= a.liquidatable_accounts
    assert b.residual_bad_debt_usd8 >= a.residual_bad_debt_usd8
