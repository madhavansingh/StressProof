"""
Part 4 tests: synth -> normalize -> sweep (implementationplan.md §9.5, §9.6, §9.8, §12.5).
Every test writes into a temporary DATA_DIR; nothing touches data/datasets/.
"""

import json
import subprocess

import pytest

from stressproof_core import canonical_bytes, keccak256_hex, replay
from stressproof_core.constants import BPS
from stressproof_pipeline import datafiles
from stressproof_pipeline.datafiles import PipelineError, git_commit, write_jsonl
from stressproof_pipeline.normalization import normalize, sweep, synth
from stressproof_pipeline.normalization.normalize import data_class_for, merge_accounts
from stressproof_pipeline.normalization.sweep import select_shock, sweep_table
from stressproof_pipeline.paths import dataset_dir

APPENDIX_A_ACCOUNTS = [
    ("10000000000000000000", "2000000000000"),
    ("5000000000000000000", "1200000000000"),
    ("10000000000000000000", "1000000000000"),
    ("1000000000000000000", "174300000000"),
    ("1000000000000000000", "174300000001"),
    ("1", "1"),
]
WETH = {"bonusBps": 10500, "decimals": 18, "ltBps": 8300, "priceUsd8": "300000000000"}


def snapshot_of(accounts, assets=WETH):
    return {
        "accounts": [
            {"collateralAmount": c, "debtUsd8": d, "id": f"synth-{i:04d}", "origin": "synthetic"}
            for i, (c, d) in enumerate(accounts, start=1)
        ],
        "assets": {"WETH": assets},
    }


def real_account(n, collateral="1000000000000000000", debt="100000000000"):
    return {"collateralAmount": collateral, "debtUsd8": debt, "id": f"0x{n:040x}", "origin": "real_aave_v3_fork"}


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(normalize, "git_commit", lambda allow_dirty: "a" * 40)
    return tmp_path


# --- synth ---------------------------------------------------------------------

def test_synth_same_seed_same_bytes():
    a = canonical_bytes(synth.generate_synthetic_accounts(42, 40))
    b = canonical_bytes(synth.generate_synthetic_accounts(42, 40))
    assert a == b
    assert canonical_bytes(synth.generate_synthetic_accounts(43, 40)) != a


def test_synth_cli_writes_identical_files_for_same_seed(data_root):
    assert synth.main(["--seed", "7", "--count", "25"]) == 0
    out = dataset_dir("weth-stable-synth-7-v1")
    first = {p.name: p.read_bytes() for p in out.iterdir()}
    assert set(first) == {"synthetic_accounts.jsonl", "assets.json", "dataset_manifest.draft.json"}
    assert synth.main(["--seed", "7", "--count", "25"]) == 0
    assert {p.name: p.read_bytes() for p in out.iterdir()} == first
    draft = json.loads(first["dataset_manifest.draft.json"])
    assert draft["dataClass"] == "SYNTHETIC" and draft["syntheticSeed"] == 7
    assert draft["datasetId"] == "weth-stable-synth-7-v1"


@pytest.mark.parametrize("lt_bps", [4100, 8300, 9999])
def test_every_synth_account_healthy_at_unshocked_price(lt_bps):
    price = 300000000000
    for acc in synth.generate_synthetic_accounts(42, 200, price_usd8=price, lt_bps=lt_bps):
        collateral = int(acc["collateralAmount"])
        assert collateral % 10**18 == 0 and collateral > 0
        cval0 = collateral * price // 10**18
        assert not (cval0 * lt_bps // BPS) < int(acc["debtUsd8"]), acc
        ltv = int(acc["debtUsd8"]) * BPS // cval0
        assert 4000 - 1 <= ltv <= lt_bps - 100
        assert acc["origin"] == "synthetic" and acc["id"].startswith("synth-")


def test_synth_ids_are_sequential():
    ids = [a["id"] for a in synth.generate_synthetic_accounts(1, 12)]
    assert ids == [f"synth-{i:04d}" for i in range(1, 13)]


@pytest.mark.parametrize("args", [["--count", "0"], ["--count", "10000"], ["--lt-bps", "9999", "--bonus-bps", "10500"],
                                  ["--price-usd8", "0"], ["--dataset", "Bad_ID"]])
def test_synth_rejects_invalid_input(data_root, args):
    assert synth.main(args) == 1


# --- normalize -------------------------------------------------------------------

def make_synthetic_dataset(seed=42, count=40):
    assert synth.main(["--seed", str(seed), "--count", str(count)]) == 0
    return f"weth-stable-synth-{seed}-v1"


def test_normalize_is_idempotent_and_hash_matches(data_root):
    dataset_id = make_synthetic_dataset()
    out = dataset_dir(dataset_id)
    assert normalize.main(["--dataset", dataset_id]) == 0
    snapshot_1 = (out / "snapshot.json").read_bytes()
    manifest_1 = (out / "dataset_manifest.json").read_bytes()
    assert normalize.main(["--dataset", dataset_id]) == 0
    assert (out / "snapshot.json").read_bytes() == snapshot_1
    assert (out / "dataset_manifest.json").read_bytes() == manifest_1
    manifest = json.loads(manifest_1)
    assert keccak256_hex(snapshot_1) == manifest["snapshotHash"]
    assert manifest["counts"] == {"real": 0, "synthetic": 40}
    assert manifest["dataClass"] == "SYNTHETIC"
    assert manifest["extractedAt"].endswith("Z") and "." not in manifest["extractedAt"]
    assert canonical_bytes(json.loads(snapshot_1)) == snapshot_1


def test_normalize_rejects_duplicate_ids(data_root):
    dataset_id = make_synthetic_dataset(count=3)
    path = dataset_dir(dataset_id) / "synthetic_accounts.jsonl"
    records = [json.loads(line) for line in path.read_bytes().splitlines()]
    write_jsonl(path, records + [records[0]])
    assert normalize.main(["--dataset", dataset_id]) == 1
    assert not (dataset_dir(dataset_id) / "snapshot.json").exists()


def test_merge_rejects_duplicate_across_real_and_synthetic():
    acc = real_account(1)
    with pytest.raises(PipelineError, match="duplicate"):
        merge_accounts([acc], [dict(acc)])


def test_normalize_drops_zero_collateral_and_counts_it(data_root):
    dataset_id = make_synthetic_dataset(count=5)
    path = dataset_dir(dataset_id) / "synthetic_accounts.jsonl"
    records = [json.loads(line) for line in path.read_bytes().splitlines()]
    records[2]["collateralAmount"] = "0"
    write_jsonl(path, records)
    assert normalize.main(["--dataset", dataset_id]) == 0
    manifest = json.loads((dataset_dir(dataset_id) / "dataset_manifest.json").read_bytes())
    assert manifest["counts"]["synthetic"] == 4
    assert manifest["excludedCounts"]["other"] == 1


@pytest.mark.parametrize("bad", ["01", "1.5", "-1", "", "abc"])
def test_normalize_rejects_non_canonical_amounts(data_root, bad):
    dataset_id = make_synthetic_dataset(count=3)
    path = dataset_dir(dataset_id) / "synthetic_accounts.jsonl"
    records = [json.loads(line) for line in path.read_bytes().splitlines()]
    records[0]["debtUsd8"] = bad
    write_jsonl(path, records)
    assert normalize.main(["--dataset", dataset_id]) == 1


def test_normalize_sorts_by_id(data_root):
    dataset_id = make_synthetic_dataset(count=10)
    path = dataset_dir(dataset_id) / "synthetic_accounts.jsonl"
    records = [json.loads(line) for line in path.read_bytes().splitlines()]
    write_jsonl(path, list(reversed(records)))
    assert normalize.main(["--dataset", dataset_id]) == 0
    snapshot = json.loads((dataset_dir(dataset_id) / "snapshot.json").read_bytes())
    ids = [a["id"] for a in snapshot["accounts"]]
    assert ids == sorted(ids)


def test_data_class_rules():
    assert data_class_for(5, 0) == "REAL"
    assert data_class_for(5, 3) == "MIXED"
    assert data_class_for(0, 3) == "SYNTHETIC"
    with pytest.raises(PipelineError):
        data_class_for(0, 0)


def _real_dataset(n_real, dataset_id="weth-stable-19000000-v1"):
    out = dataset_dir(dataset_id)
    draft = synth.synthetic_draft_manifest(dataset_id, seed=0)
    draft.update({"dataClass": "REAL", "syntheticSeed": None, "network": "ethereum-mainnet-fork", "forkBlock": 19000000})
    datafiles.write_canonical(out / "dataset_manifest.draft.json", draft)
    datafiles.write_canonical(out / "assets.json", {"WETH": WETH})
    write_jsonl(out / "real_accounts.jsonl", [real_account(i + 1) for i in range(n_real)])
    return dataset_id


def test_real_dataset_needs_20_accounts(data_root):
    dataset_id = _real_dataset(19)
    assert normalize.main(["--dataset", dataset_id]) == 1
    dataset_id = _real_dataset(20, "weth-stable-19000001-v1")
    assert normalize.main(["--dataset", dataset_id]) == 0
    manifest = json.loads((dataset_dir(dataset_id) / "dataset_manifest.json").read_bytes())
    assert manifest["dataClass"] == "REAL" and manifest["counts"] == {"real": 20, "synthetic": 0}


def test_real_plus_synth_is_mixed_and_records_seed(data_root):
    dataset_id = _real_dataset(5)
    assert synth.main(["--dataset", dataset_id, "--seed", "9", "--count", "20"]) == 0
    assert normalize.main(["--dataset", dataset_id]) == 0
    manifest = json.loads((dataset_dir(dataset_id) / "dataset_manifest.json").read_bytes())
    assert manifest["dataClass"] == "MIXED"
    assert manifest["counts"] == {"real": 5, "synthetic": 20}
    assert manifest["syntheticSeed"] == 9
    snapshot = json.loads((dataset_dir(dataset_id) / "snapshot.json").read_bytes())
    assert snapshot["accounts"][0]["origin"] == "real_aave_v3_fork"   # 0x… sorts before synth-…


def test_synth_cannot_override_real_asset_params(data_root):
    dataset_id = _real_dataset(5)
    assert synth.main(["--dataset", dataset_id, "--price-usd8", "1"]) == 1


def test_manifest_has_every_plan_key(data_root):
    dataset_id = make_synthetic_dataset(count=3)
    assert normalize.main(["--dataset", dataset_id]) == 0
    manifest = json.loads((dataset_dir(dataset_id) / "dataset_manifest.json").read_bytes())
    assert set(manifest) == normalize.MANIFEST_KEYS
    assert manifest["extractionScriptCommit"] == "a" * 40


def test_missing_dataset_and_missing_argument(data_root, monkeypatch):
    assert normalize.main(["--dataset", "does-not-exist"]) == 1
    # main() calls load_env(), which would restore DATASET_ID from a developer's <repo>/.env.
    # Stub it so this really is "no --dataset and no DATASET_ID".
    monkeypatch.setattr(normalize, "load_env", lambda: None)
    monkeypatch.delenv("DATASET_ID", raising=False)
    with pytest.raises(SystemExit):
        normalize.main([])


# --- dirty-tree gate ----------------------------------------------------------------

def _fake_git(porcelain):
    def run(cmd, **kwargs):
        out = "f" * 40 + "\n" if cmd[1] == "rev-parse" else porcelain
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
    return run


def test_dirty_tree_refused_unless_allowed(monkeypatch):
    monkeypatch.setattr(datafiles.subprocess, "run", _fake_git(" M core/x.py\n"))
    with pytest.raises(PipelineError, match="dirty"):
        git_commit(allow_dirty=False)
    assert git_commit(allow_dirty=True) == "f" * 40 + "-dirty"


def test_clean_tree_records_plain_commit(monkeypatch):
    monkeypatch.setattr(datafiles.subprocess, "run", _fake_git(""))
    assert git_commit(allow_dirty=False) == "f" * 40


# --- secrets guard ---------------------------------------------------------------------

def test_outputs_never_contain_urls_or_secret_values(tmp_path, monkeypatch):
    with pytest.raises(PipelineError, match="URL"):
        datafiles.write_canonical(tmp_path / "m.json", {"rpcProvider": "https://eth.example/v2/key"})
    monkeypatch.setenv("ATTESTER_PK", "0x" + "12" * 32)
    with pytest.raises(PipelineError, match="ATTESTER_PK"):
        datafiles.write_canonical(tmp_path / "m.json", {"note": "0x" + "12" * 32})
    assert not (tmp_path / "m.json").exists()


# --- sweep -------------------------------------------------------------------------------

def test_sweep_shock_list():
    assert sweep.SHOCKS[0] == -1000 and sweep.SHOCKS[-1] == -9000 and len(sweep.SHOCKS) == 17


def test_sweep_appendix_a_picks_minus_3000():
    result = sweep.run_shock_sweep(snapshot_of(APPENDIX_A_ACCOUNTS))
    assert result["chosen"]["shockBps"] == -3000
    assert result["R"] == 200000000001
    assert result["thresholds"] == {"ltvThresholdUsd8": "100000000000", "pauseThresholdUsd8": "400000000002"}
    by_shock = {row["shockBps"]: row for row in result["table"]}
    assert by_shock[-1000]["qualifies"]            # residual 1, 2 liquidatable: qualifies but -3000 is preferred
    assert by_shock[-3000]["residualBadDebtUsd8"] == "200000000001"


def test_sweep_falls_back_to_smallest_qualifying_shock():
    # One account goes underwater only beyond -3000; another becomes liquidatable early.
    # At -1000..-3000 only one account is liquidatable, so -3000 does not qualify.
    accounts = [
        ("1000000000000000000", "160000000000"),   # $3,000 collateral, $1,600 debt
        ("1000000000000000000", "140000000000"),   # $3,000 collateral, $1,400 debt
    ]
    rows = sweep_table(snapshot_of(accounts))
    assert not {row["shockBps"]: row for row in rows}[-3000]["qualifies"]
    chosen = select_shock(rows)
    qualifying = [row["shockBps"] for row in rows if row["qualifies"]]
    assert chosen["shockBps"] == max(qualifying)          # smallest magnitude
    assert chosen["shockBps"] < -3000
    expected = replay({"scenario": {"asset": "WETH", "shockBps": chosen["shockBps"]}, "snapshot": snapshot_of(accounts)})
    assert chosen["residualBadDebtUsd8"] == str(expected.residual_bad_debt_usd8)


def test_select_shock_unit_rules():
    def row(shock, q):
        return {"shockBps": shock, "qualifies": q, "residualBadDebtUsd8": "10"}
    assert select_shock([row(-1000, True), row(-3000, True)])["shockBps"] == -3000
    assert select_shock([row(-1000, False), row(-2500, True), row(-4000, True)])["shockBps"] == -2500
    assert select_shock([row(-1000, False), row(-3000, False)]) is None


def test_sweep_cli_end_to_end_and_no_qualifying_shock(data_root, capsys):
    dataset_id = make_synthetic_dataset()
    assert normalize.main(["--dataset", dataset_id]) == 0
    assert sweep.main(["--dataset", dataset_id]) == 0
    printed = capsys.readouterr().out
    result = json.loads((dataset_dir(dataset_id) / "sweep.json").read_bytes())
    r = int(result["residualBadDebtUsd8"])
    assert f"FIXED_SCENARIO_SHOCK_BPS={result['chosenShockBps']}" in printed
    assert f"LTV_THRESHOLD_USD8={r // 2}" in printed
    assert f"PAUSE_THRESHOLD_USD8={2 * r}" in printed
    assert len(result["table"]) == 17

    # A healthy-at-every-shock dataset (tiny debts) must fail loudly and write nothing.
    out = dataset_dir(dataset_id)
    write_jsonl(out / "synthetic_accounts.jsonl",
                [{"collateralAmount": "1000000000000000000", "debtUsd8": "1", "id": "synth-0001", "origin": "synthetic"}])
    (out / "sweep.json").unlink()
    assert normalize.main(["--dataset", dataset_id]) == 0
    assert sweep.main(["--dataset", dataset_id]) == 1
    assert not (out / "sweep.json").exists()


def test_sweep_refuses_tampered_snapshot(data_root):
    dataset_id = make_synthetic_dataset(count=5)
    assert normalize.main(["--dataset", dataset_id]) == 0
    path = dataset_dir(dataset_id) / "snapshot.json"
    path.write_bytes(path.read_bytes().replace(b'"synth-0001"', b'"synth-0009"'))
    assert sweep.main(["--dataset", dataset_id]) == 1
