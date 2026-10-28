"""
The fixture generator must rebuild the committed golden fixture byte for byte.
"""

from stressproof_pipeline.fixtures import FIXTURES_DIR, GOLDEN, build_fixture, main


def test_generator_reproduces_committed_files():
    for name, data in build_fixture().items():
        assert (FIXTURES_DIR / name).read_bytes() == data, name


def test_generator_is_deterministic():
    assert build_fixture() == build_fixture()


def test_verify_mode_passes_on_committed_fixtures():
    assert main([]) == 0


def test_refuses_to_continue_when_golden_differs(tmp_path):
    files = build_fixture()
    for name in GOLDEN:
        (tmp_path / name).write_bytes(files[name])
    (tmp_path / "casefile_v1.json").write_bytes(files["casefile_v1.json"] + b" ")
    assert main(["--dir", str(tmp_path), "--write"]) == 1
    assert not (tmp_path / "snapshot_v1.json").exists()


def test_write_mode_creates_derived_files(tmp_path):
    files = build_fixture()
    for name in GOLDEN:
        (tmp_path / name).write_bytes(files[name])
    assert main(["--dir", str(tmp_path), "--write"]) == 0
    for name, data in files.items():
        assert (tmp_path / name).read_bytes() == data
