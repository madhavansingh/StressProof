"""
Tests for snapshot pipeline normalization.
"""

from stressproof_pipeline.normalization.synth import generate_synthetic_accounts
from stressproof_pipeline.normalization.normalize import normalize_dataset


def test_synthetic_account_generation():
    accounts = generate_synthetic_accounts(seed=42, count=5)
    assert len(accounts) == 5
    assert accounts[0]["id"] == "synth-0001"
    assert accounts[0]["origin"] == "synthetic"
    assert int(accounts[0]["collateralAmount"]) > 0


def test_normalize_dataset_ordering():
    real = [{"id": "0x0000000000000000000000000000000000000002", "collateralAmount": "10", "debtUsd8": "5", "origin": "real_aave_v3_fork"}]
    synth = [{"id": "synth-0001", "collateralAmount": "20", "debtUsd8": "10", "origin": "synthetic"}]
    assets = {"WETH": {"priceUsd8": "300000000000", "decimals": 18, "ltBps": 8300, "bonusBps": 10500}}

    snapshot, b, h = normalize_dataset(real, synth, assets, {})
    assert snapshot["accounts"][0]["id"] == "0x0000000000000000000000000000000000000002"
    assert snapshot["accounts"][1]["id"] == "synth-0001"
    assert h.startswith("0x")
