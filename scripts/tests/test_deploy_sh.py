"""Tests for scripts/deploy.sh failure paths. No chain, no forge and no network are used:
forge is replaced by a stub, and every case must leave deployments/31337.json untouched.

Run: .venv/bin/python -m pytest scripts/tests -p no:cacheprovider
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SH = REPO_ROOT / "scripts" / "deploy.sh"
DEPLOYMENTS_FILE = REPO_ROOT / "deployments" / "31337.json"
BROADCAST_FILE = REPO_ROOT / "contracts" / "broadcast" / "Deploy.s.sol" / "31337" / "run-latest.json"
SHELL = "/bin/bash"
GIT = "/usr/bin/git" if os.path.exists("/usr/bin/git") else "git"
UV = shutil.which("uv")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stub(tmp_path: Path, name: str, exit_code: int) -> Path:
    path = tmp_path / name
    path.write_text(f"#!/bin/sh\necho 'stub {name} called' >&2\nexit {exit_code}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _env_file(tmp_path: Path) -> Path:
    path = tmp_path / "test.env"
    path.write_text("MARKET_ID_STRING=aave-v3-eth-weth-stable\nLOCAL_RPC_URL=http://127.0.0.1:1\n")
    return path


def _run(*args: str, **env: str) -> subprocess.CompletedProcess:
    full_env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), "GIT": GIT, **env}
    return subprocess.run([SHELL, str(DEPLOY_SH), *args], capture_output=True, text=True, env=full_env, timeout=120)


@pytest.fixture(autouse=True)
def deployments_file_is_untouched():
    before = _digest(DEPLOYMENTS_FILE)
    yield
    assert _digest(DEPLOYMENTS_FILE) == before


def test_usage_error_without_target():
    result = _run()
    assert result.returncode == 2
    assert "Usage" in result.stderr


def test_unknown_target_is_rejected():
    assert _run("mainnet").returncode == 2


def test_missing_env_file(tmp_path):
    result = _run("local", ENV_FILE=str(tmp_path / "missing.env"))
    assert result.returncode == 1
    assert "not found" in result.stderr and "NOT written" in result.stderr


def test_git_failure_stops_before_deploying(tmp_path):
    forge = _stub(tmp_path, "forge", 0)
    result = _run("local", ENV_FILE=str(_env_file(tmp_path)), GIT="/usr/bin/false", FORGE=str(forge))
    assert result.returncode == 1
    assert "git status failed" in result.stderr
    assert "stub forge called" not in result.stderr


def test_failed_forge_broadcast_writes_nothing(tmp_path):
    forge = _stub(tmp_path, "forge", 1)
    result = _run("local", ENV_FILE=str(_env_file(tmp_path)), FORGE=str(forge))
    assert result.returncode == 1
    assert "stub forge called" in result.stderr
    assert "forge script failed" in result.stderr


@pytest.mark.skipif(UV is None, reason="uv not installed")
@pytest.mark.skipif(BROADCAST_FILE.exists(), reason="a real broadcast record exists; covered by the mtime unit test")
def test_forge_success_without_broadcast_record_writes_nothing(tmp_path):
    """Like a dry run: forge exits 0 but there is no broadcast record to confirm."""
    forge = _stub(tmp_path, "forge", 0)
    result = _run("local", ENV_FILE=str(_env_file(tmp_path)), FORGE=str(forge), UV=UV)
    assert result.returncode == 1
    assert "broadcast record not found" in result.stderr
    assert "could not be confirmed" in result.stderr


def test_testnet_requires_rpc_url(tmp_path):
    result = _run("testnet", ENV_FILE=str(_env_file(tmp_path)), FORGE=str(_stub(tmp_path, "forge", 0)))
    assert result.returncode == 1
    assert "TESTNET_RPC_URL is not set" in result.stderr
