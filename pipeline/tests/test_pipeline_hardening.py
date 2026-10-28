"""
Part 4 hardening regressions: atomic writes, structure checks with clean CLI errors,
synth dataset states, and the stale-sweep policy. All tests use a temporary DATA_DIR.
"""

import json
import os
import threading

import pytest

from stressproof_core import keccak256_hex
from stressproof_pipeline import datafiles
from stressproof_pipeline.datafiles import (
    PipelineError,
    atomic_write,
    check_account,
    check_assets,
    check_manifest,
    read_jsonl,
    write_canonical,
    write_jsonl,
)
from stressproof_pipeline.normalization import normalize, sweep, synth
from stressproof_pipeline.paths import dataset_dir

WETH = {"bonusBps": 10500, "decimals": 18, "ltBps": 8300, "priceUsd8": "300000000000"}


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(normalize, "git_commit", lambda allow_dirty: "a" * 40)
    return tmp_path


def snapshot_files(directory):
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())} if directory.exists() else {}


def synthetic_dataset(seed=42, count=40):
    assert synth.main(["--seed", str(seed), "--count", str(count)]) == 0
    return f"weth-stable-synth-{seed}-v1"


# --- atomic writes ---------------------------------------------------------------

def test_atomic_write_failure_preserves_destination_and_cleans_up(tmp_path, monkeypatch):
    target = tmp_path / "out.json"
    target.write_bytes(b"original")

    def broken_fsync(fd):
        raise OSError("disk full")
    monkeypatch.setattr(datafiles.os, "fsync", broken_fsync)
    with pytest.raises(OSError, match="disk full"):
        atomic_write(target, b"replacement")
    assert target.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_atomic_write_replace_failure_cleans_up(tmp_path, monkeypatch):
    target = tmp_path / "out.json"
    target.write_bytes(b"original")

    def broken_replace(src, dst):
        raise OSError("replace failed")
    monkeypatch.setattr(datafiles.os, "replace", broken_replace)
    with pytest.raises(OSError):
        atomic_write(target, b"replacement")
    assert target.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_atomic_write_uses_unique_temp_files(tmp_path, monkeypatch):
    seen = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append(os.path.basename(src))
        real_replace(src, dst)
    monkeypatch.setattr(datafiles.os, "replace", spy)
    atomic_write(tmp_path / "a.json", b"1")
    atomic_write(tmp_path / "a.json", b"2")
    assert len(set(seen)) == 2 and all(name.startswith(".a.json.") for name in seen)


def test_atomic_write_concurrent_writers_never_corrupt(tmp_path):
    target = tmp_path / "shared.json"
    payloads = [bytes([65 + i]) * 50_000 for i in range(8)]
    errors = []

    def writer(data):
        try:
            for _ in range(5):
                atomic_write(target, data)
        except Exception as e:   # pragma: no cover - reported below
            errors.append(e)
    threads = [threading.Thread(target=writer, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert target.read_bytes() in payloads
    assert [p.name for p in tmp_path.iterdir()] == ["shared.json"]


# --- readers and account checks --------------------------------------------------------

def test_read_jsonl_missing_file_is_pipeline_error(tmp_path):
    with pytest.raises(PipelineError, match="missing file"):
        read_jsonl(tmp_path / "nope.jsonl")


def test_check_account_rejects_unsupported_origin():
    acc = {"collateralAmount": "1", "debtUsd8": "1", "id": "synth-0001", "origin": "synthetic"}
    with pytest.raises(PipelineError, match="unsupported origin"):
        check_account(acc, "made_up", "here")


@pytest.mark.parametrize("record", [None, [], {"id": "synth-0001"}, {"collateralAmount": 1, "debtUsd8": "1",
                                                                     "id": "synth-0001", "origin": "synthetic"}])
def test_check_account_rejects_malformed_records(record):
    with pytest.raises(PipelineError):
        check_account(record, "synthetic", "here")


# --- asset and manifest checks ----------------------------------------------------------

@pytest.mark.parametrize("mutate", [
    lambda a: a.pop("WETH"),
    lambda a: a.__setitem__("WBTC", dict(WETH)),
    lambda a: a.__setitem__("WETH", []),
    lambda a: a["WETH"].pop("ltBps"),
    lambda a: a["WETH"].__setitem__("ltBps", True),
    lambda a: a["WETH"].__setitem__("ltBps", "8300"),
    lambda a: a["WETH"].__setitem__("ltBps", 0),
    lambda a: a["WETH"].__setitem__("bonusBps", 10000),
    lambda a: a["WETH"].__setitem__("ltBps", 9600),          # 9600 * 10500 > 100%
    lambda a: a["WETH"].__setitem__("decimals", 6),
    lambda a: a["WETH"].__setitem__("priceUsd8", 300000000000),
    lambda a: a["WETH"].__setitem__("priceUsd8", "0"),
    lambda a: a["WETH"].__setitem__("priceUsd8", "03"),
])
def test_check_assets_rejects_malformed_weth(mutate):
    assets = {"WETH": dict(WETH)}
    mutate(assets)
    with pytest.raises(PipelineError):
        check_assets(assets)


def test_check_assets_accepts_valid():
    assert check_assets({"WETH": dict(WETH)})["WETH"]["ltBps"] == 8300


def _draft():
    return synth.synthetic_draft_manifest("weth-stable-synth-1-v1", 1)


@pytest.mark.parametrize("mutate", [
    lambda m: m.pop("counts"),
    lambda m: m.__setitem__("extra", 1),
    lambda m: m.__setitem__("excludedCounts", []),
    lambda m: m["excludedCounts"].pop("other"),
    lambda m: m["excludedCounts"].__setitem__("other", -1),
    lambda m: m["excludedCounts"].__setitem__("other", True),
    lambda m: m["excludedCounts"].__setitem__("other", "0"),
    lambda m: m["counts"].__setitem__("real", None),
    lambda m: m.__setitem__("forkBlock", "0"),
    lambda m: m.__setitem__("syntheticSeed", False),
    lambda m: m.__setitem__("dataClass", "FAKE"),
    lambda m: m.__setitem__("stablecoinAllowlist", {}),
    lambda m: m.__setitem__("stablecoinAllowlist", [{"address": "0x1"}]),
    lambda m: m.__setitem__("network", 5),
])
def test_check_manifest_rejects_invalid_fields(mutate):
    manifest = _draft()
    mutate(manifest)
    with pytest.raises(PipelineError):
        check_manifest(manifest, "draft", final=False)


def test_final_manifest_requires_provenance_and_hash():
    with pytest.raises(PipelineError, match="snapshotHash"):
        check_manifest(_draft(), "m", final=True)
    assert check_manifest(_draft(), "draft", final=False)


# --- normalize: malformed inputs exit cleanly ---------------------------------------------

@pytest.mark.parametrize("target,mutate", [
    ("dataset_manifest.draft.json", lambda m: m["excludedCounts"].pop("other")),
    ("dataset_manifest.draft.json", lambda m: m["excludedCounts"].__setitem__("other", True)),
    ("dataset_manifest.draft.json", lambda m: m.pop("filter")),
    ("dataset_manifest.draft.json", lambda m: m.__setitem__("counts", [])),
    ("assets.json", lambda a: a["WETH"].pop("bonusBps")),
    ("assets.json", lambda a: a.__setitem__("WETH", "x")),
])
def test_normalize_malformed_inputs_exit_cleanly(data_root, capsys, target, mutate):
    dataset_id = synthetic_dataset(count=3)
    path = dataset_dir(dataset_id) / target
    obj = json.loads(path.read_bytes())
    mutate(obj)
    write_canonical(path, obj)
    assert normalize.main(["--dataset", dataset_id]) == 1
    assert "normalize: error:" in capsys.readouterr().err
    assert not (dataset_dir(dataset_id) / "snapshot.json").exists()


def test_normalize_replaces_unreadable_previous_manifest(data_root):
    dataset_id = synthetic_dataset(count=3)
    (dataset_dir(dataset_id) / "dataset_manifest.json").write_bytes(b"{not json")
    assert normalize.main(["--dataset", dataset_id]) == 0
    check_manifest(json.loads((dataset_dir(dataset_id) / "dataset_manifest.json").read_bytes()), "m", final=True)


# --- synth: invalid parameters leave the dataset untouched ---------------------------------

@pytest.mark.parametrize("args", [
    ["--count", "0"], ["--count", "10000"], ["--seed", "-1"], ["--price-usd8", "0"], ["--price-usd8", "-5"],
    ["--lt-bps", "4000"], ["--lt-bps", "10000"], ["--bonus-bps", "10000"], ["--bonus-bps", "15001"],
    ["--lt-bps", "9999", "--bonus-bps", "10500"],
])
def test_invalid_synth_parameters_write_nothing(data_root, args):
    assert synth.main(["--seed", "5", *args]) == 1
    assert snapshot_files(dataset_dir("weth-stable-synth-5-v1")) == {}


def test_invalid_synth_parameters_do_not_modify_existing_dataset(data_root):
    dataset_id = synthetic_dataset(seed=5, count=10)
    before = snapshot_files(dataset_dir(dataset_id))
    assert synth.main(["--seed", "5", "--count", "0"]) == 1
    assert synth.main(["--seed", "5", "--bonus-bps", "20000"]) == 1
    assert snapshot_files(dataset_dir(dataset_id)) == before


def _write_real_dataset(dataset_id, *, assets=True, draft=True, accounts=True, draft_overrides=None):
    out = dataset_dir(dataset_id)
    out.mkdir(parents=True, exist_ok=True)
    manifest = synth.synthetic_draft_manifest(dataset_id, 0)
    manifest.update({"dataClass": "REAL", "syntheticSeed": None, "network": "ethereum-mainnet-fork"})
    manifest.update(draft_overrides or {})
    if draft:
        write_canonical(out / "dataset_manifest.draft.json", manifest)
    if assets:
        write_canonical(out / "assets.json", {"WETH": dict(WETH)})
    if accounts:
        write_jsonl(out / "real_accounts.jsonl", [
            {"collateralAmount": "1000000000000000000", "debtUsd8": "1", "id": f"0x{i:040x}", "origin": "real_aave_v3_fork"}
            for i in range(1, 4)
        ])
    return out


@pytest.mark.parametrize("missing", ["assets", "draft"])
def test_synth_rejects_real_dataset_missing_pin_outputs(data_root, missing):
    out = _write_real_dataset("weth-stable-1-v1", **{missing: False})
    before = snapshot_files(out)
    assert synth.main(["--dataset", "weth-stable-1-v1", "--seed", "3"]) == 1
    assert snapshot_files(out) == before


@pytest.mark.parametrize("keep", ["assets", "draft"])
def test_synth_rejects_half_configured_dataset(data_root, keep):
    out = _write_real_dataset("weth-stable-2-v1", accounts=False, **{("draft" if keep == "assets" else "assets"): False})
    before = snapshot_files(out)
    assert synth.main(["--dataset", "weth-stable-2-v1"]) == 1
    assert snapshot_files(out) == before


def test_synth_refuses_to_overwrite_real_draft_without_real_accounts(data_root):
    out = _write_real_dataset("weth-stable-3-v1", accounts=False)
    before = snapshot_files(out)
    assert synth.main(["--dataset", "weth-stable-3-v1"]) == 1
    assert snapshot_files(out) == before


def test_synth_rejects_inconsistent_real_draft(data_root):
    out = _write_real_dataset("weth-stable-4-v1", draft_overrides={"datasetId": "other-id"})
    before = snapshot_files(out)
    assert synth.main(["--dataset", "weth-stable-4-v1"]) == 1
    out2 = _write_real_dataset("weth-stable-5-v1")
    write_canonical(out2 / "assets.json", {"WETH": {**WETH, "ltBps": True}})
    before2 = snapshot_files(out2)
    assert synth.main(["--dataset", "weth-stable-5-v1"]) == 1
    assert snapshot_files(out) == before and snapshot_files(out2) == before2


def test_synth_on_valid_real_dataset_only_records_seed(data_root):
    out = _write_real_dataset("weth-stable-6-v1")
    assets_before = (out / "assets.json").read_bytes()
    assert synth.main(["--dataset", "weth-stable-6-v1", "--seed", "11", "--count", "5"]) == 0
    assert (out / "assets.json").read_bytes() == assets_before
    draft = json.loads((out / "dataset_manifest.draft.json").read_bytes())
    assert draft["syntheticSeed"] == 11 and draft["dataClass"] == "REAL"
    assert len((out / "synthetic_accounts.jsonl").read_bytes().splitlines()) == 5


# --- sweep: validation and stale output ------------------------------------------------------

def _normalized(count=40):
    dataset_id = synthetic_dataset(count=count)
    assert normalize.main(["--dataset", dataset_id]) == 0
    return dataset_id


def test_sweep_rejects_malformed_manifest_cleanly(data_root, capsys):
    dataset_id = _normalized(count=5)
    path = dataset_dir(dataset_id) / "dataset_manifest.json"
    manifest = json.loads(path.read_bytes())
    del manifest["counts"]
    write_canonical(path, manifest)
    assert sweep.main(["--dataset", dataset_id]) == 1
    assert "sweep: error:" in capsys.readouterr().err


def test_sweep_rejects_malformed_snapshot_cleanly(data_root, capsys):
    dataset_id = _normalized(count=5)
    out = dataset_dir(dataset_id)
    bad = {"accounts": [{"id": "synth-0001"}], "assets": {"WETH": dict(WETH)}}
    data = write_canonical(out / "snapshot.json", bad)
    manifest = json.loads((out / "dataset_manifest.json").read_bytes())
    manifest["snapshotHash"] = keccak256_hex(data)
    write_canonical(out / "dataset_manifest.json", manifest)
    assert sweep.main(["--dataset", dataset_id]) == 1
    assert "sweep: error:" in capsys.readouterr().err


def test_failed_sweep_retires_previous_output_instead_of_deleting(data_root, capsys):
    dataset_id = _normalized()
    out = dataset_dir(dataset_id)
    assert sweep.main(["--dataset", dataset_id]) == 0
    previous = (out / "sweep.json").read_bytes()

    # New inputs where no shock qualifies.
    write_jsonl(out / "synthetic_accounts.jsonl",
                [{"collateralAmount": "1000000000000000000", "debtUsd8": "1", "id": "synth-0001", "origin": "synthetic"}])
    assert normalize.main(["--dataset", dataset_id]) == 0
    assert sweep.main(["--dataset", dataset_id]) == 1
    err = capsys.readouterr().err
    assert "sweep.stale.json" in err
    assert not (out / "sweep.json").exists()
    assert (out / "sweep.stale.json").read_bytes() == previous
    stale = json.loads(previous)
    current = json.loads((out / "dataset_manifest.json").read_bytes())
    assert stale["snapshotHash"] != current["snapshotHash"]


def test_failed_sweep_without_previous_output_writes_nothing(data_root):
    dataset_id = synthetic_dataset(count=1)
    out = dataset_dir(dataset_id)
    write_jsonl(out / "synthetic_accounts.jsonl",
                [{"collateralAmount": "1000000000000000000", "debtUsd8": "1", "id": "synth-0001", "origin": "synthetic"}])
    assert normalize.main(["--dataset", dataset_id]) == 0
    assert sweep.main(["--dataset", dataset_id]) == 1
    assert not (out / "sweep.json").exists() and not (out / "sweep.stale.json").exists()


def test_successful_sweep_after_failure_writes_fresh_output(data_root):
    dataset_id = _normalized()
    out = dataset_dir(dataset_id)
    (out / "sweep.stale.json").write_bytes(b"old")
    assert sweep.main(["--dataset", dataset_id]) == 0
    result = json.loads((out / "sweep.json").read_bytes())
    assert result["snapshotHash"] == json.loads((out / "dataset_manifest.json").read_bytes())["snapshotHash"]


# --- synth must never start over a finalized dataset -----------------------------------------

@pytest.mark.parametrize("present", [("snapshot.json",), ("dataset_manifest.json",), ("snapshot.json", "dataset_manifest.json")])
def test_synth_refuses_finalized_dataset_without_inputs(data_root, present):
    out = dataset_dir("weth-stable-19000000-v1")
    out.mkdir(parents=True)
    for name in present:
        (out / name).write_bytes(b'{"dataClass":"REAL"}')
    before = snapshot_files(out)
    assert synth.main(["--dataset", "weth-stable-19000000-v1"]) == 1
    assert snapshot_files(out) == before


def test_synth_refuses_synthetic_inputs_next_to_non_synthetic_manifest(data_root):
    dataset_id = _normalized(count=5)
    out = dataset_dir(dataset_id)
    path = out / "dataset_manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["dataClass"] = "REAL"
    write_canonical(path, manifest)
    before = snapshot_files(out)
    assert synth.main(["--seed", "42", "--count", "5"]) == 1
    assert snapshot_files(out) == before


def test_synth_rerun_on_its_own_finalized_output_is_allowed(data_root):
    dataset_id = _normalized(count=5)
    assert synth.main(["--seed", "42", "--count", "5"]) == 0
    assert normalize.main(["--dataset", dataset_id]) == 0
