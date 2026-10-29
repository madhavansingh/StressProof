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


# ---- broadcast, record, then verify: the recording never depends on explorer verification ----

FAKE_COMMIT = "a" * 40


def _logging_stub(tmp_path: Path, name: str, log: Path, fail_when: str = "", exit_code: int = 0) -> Path:
    """A stub that appends `<name> <args>` to `log`; exits 1 when its args contain `fail_when`."""
    path = tmp_path / name
    path.write_text(
        "#!/bin/sh\n"
        f'echo "{name} $*" >> "{log}"\n'
        f'case " $* " in *"{fail_when or "<never>"}"*) exit 1 ;; esac\n'
        f"exit {exit_code}\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _clean_git(tmp_path: Path) -> Path:
    """git stub: a clean tree at a fixed commit, so the testnet path can run."""
    path = tmp_path / "git"
    path.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  status) exit 0 ;;\n"
        f"  rev-parse) echo {FAKE_COMMIT} ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _testnet_env(tmp_path: Path) -> Path:
    path = tmp_path / "testnet.env"
    path.write_text("MARKET_ID_STRING=aave-v3-eth-weth-stable\nTESTNET_RPC_URL=http://127.0.0.1:1\n")
    return path


def _calls(log: Path) -> list:
    return log.read_text().splitlines() if log.exists() else []


def test_testnet_broadcasts_without_verify_then_records_then_verifies(tmp_path):
    log = tmp_path / "calls.log"
    result = _run("testnet", ENV_FILE=str(_testnet_env(tmp_path)), GIT=str(_clean_git(tmp_path)),
                  FORGE=str(_logging_stub(tmp_path, "forge", log)), UV=str(_logging_stub(tmp_path, "uv", log)))
    assert result.returncode == 0, result.stderr
    calls = _calls(log)
    assert [c.split()[0] for c in calls] == ["uv", "forge", "uv", "forge"]
    preflight, broadcast, record, verify = calls
    assert "testnet_preflight.py" in preflight and "--keys-only" in preflight
    assert "--broadcast" in broadcast and "--verify" not in broadcast
    assert "write_deployment.py" in record and "--chain-id 84532" in record
    assert "--resume" in verify and "--verify" in verify and "--broadcast" not in verify


def test_testnet_verification_failure_keeps_the_recorded_deployment(tmp_path):
    log = tmp_path / "calls.log"
    result = _run("testnet", ENV_FILE=str(_testnet_env(tmp_path)), GIT=str(_clean_git(tmp_path)),
                  FORGE=str(_logging_stub(tmp_path, "forge", log, fail_when="--verify")),
                  UV=str(_logging_stub(tmp_path, "uv", log)))
    assert result.returncode == 0, result.stderr
    assert "verification failed" in result.stderr
    assert "deployments/84532.json was written" in result.stderr
    assert "--resume --verify" in result.stderr  # the retry command is printed
    assert "http://127.0.0.1:1" not in result.stdout + result.stderr  # the RPC URL is never echoed


def test_testnet_unconfirmed_deployment_is_never_verified(tmp_path):
    log = tmp_path / "calls.log"
    result = _run("testnet", ENV_FILE=str(_testnet_env(tmp_path)), GIT=str(_clean_git(tmp_path)),
                  FORGE=str(_logging_stub(tmp_path, "forge", log)),
                  UV=str(_logging_stub(tmp_path, "uv", log, fail_when="write_deployment")))
    assert result.returncode == 1
    assert "could not be confirmed" in result.stderr
    assert [c.split()[0] for c in _calls(log)] == ["uv", "forge", "uv"]


def test_testnet_preflight_failure_stops_before_any_broadcast(tmp_path):
    log = tmp_path / "calls.log"
    result = _run("testnet", ENV_FILE=str(_testnet_env(tmp_path)), GIT=str(_clean_git(tmp_path)),
                  FORGE=str(_logging_stub(tmp_path, "forge", log)),
                  UV=str(_logging_stub(tmp_path, "uv", log, fail_when="testnet_preflight")))
    assert result.returncode == 1
    assert "testnet preflight failed" in result.stderr
    assert "Deployments file NOT written" in result.stderr
    calls = _calls(log)
    assert len(calls) == 1 and "testnet_preflight.py" in calls[0]
    assert not any(c.startswith("forge") for c in calls)


def test_testnet_preflight_checks_the_env_file_being_deployed(tmp_path):
    log = tmp_path / "calls.log"
    env_file = _testnet_env(tmp_path)
    _run("testnet", ENV_FILE=str(env_file), GIT=str(_clean_git(tmp_path)),
         FORGE=str(_logging_stub(tmp_path, "forge", log)), UV=str(_logging_stub(tmp_path, "uv", log)))
    assert f"--env-file {env_file}" in _calls(log)[0]


def test_local_deploy_runs_no_testnet_preflight(tmp_path):
    log = tmp_path / "calls.log"
    _run("local", ENV_FILE=str(_env_file(tmp_path)), GIT=str(_clean_git(tmp_path)),
         FORGE=str(_logging_stub(tmp_path, "forge", log)), UV=str(_logging_stub(tmp_path, "uv", log)))
    assert not any("testnet_preflight" in c for c in _calls(log))


# ---- no silent duplicate deployments on testnet ----

PLACEHOLDER = '{"chainId": 84532, "registry": "0x0000000000000000000000000000000000000000"}\n'
DEPLOYED = '{"chainId": 84532, "registry": "0x5FbDB2315678afecb367f032d93F642f64180aa3"}\n'


def _dirs(tmp_path: Path, deployments_json: str, with_broadcast: bool) -> dict:
    deployments = tmp_path / "deployments"
    deployments.mkdir()
    (deployments / "84532.json").write_text(deployments_json)
    broadcast = tmp_path / "broadcast"
    if with_broadcast:
        (broadcast / "84532").mkdir(parents=True)
        (broadcast / "84532" / "run-latest.json").write_text("{}")
    return {"DEPLOYMENTS_DIR": str(deployments), "BROADCAST_DIR": str(broadcast)}


def _testnet(tmp_path: Path, log: Path, **env: str) -> subprocess.CompletedProcess:
    return _run("testnet", ENV_FILE=str(_testnet_env(tmp_path)), GIT=str(_clean_git(tmp_path)),
                FORGE=str(_logging_stub(tmp_path, "forge", log)), UV=str(_logging_stub(tmp_path, "uv", log)), **env)


def test_testnet_refuses_to_redeploy_over_a_recorded_deployment(tmp_path):
    log = tmp_path / "calls.log"
    result = _testnet(tmp_path, log, **_dirs(tmp_path, DEPLOYED, with_broadcast=True))
    assert result.returncode == 1
    assert "already records a deployment" in result.stderr and "REDEPLOY=1" in result.stderr
    assert _calls(log) == []


def test_testnet_refuses_to_broadcast_again_over_an_unrecorded_broadcast(tmp_path):
    log = tmp_path / "calls.log"
    result = _testnet(tmp_path, log, **_dirs(tmp_path, PLACEHOLDER, with_broadcast=True))
    assert result.returncode == 1
    assert "unrecorded broadcast" in result.stderr and "RECORD_ONLY=1" in result.stderr
    assert _calls(log) == []


def test_record_only_records_the_existing_broadcast_without_sending(tmp_path):
    log = tmp_path / "calls.log"
    result = _testnet(tmp_path, log, RECORD_ONLY="1", **_dirs(tmp_path, PLACEHOLDER, with_broadcast=True))
    assert result.returncode == 0, result.stderr
    calls = _calls(log)
    assert [c.split()[0] for c in calls] == ["uv", "forge"]
    assert "--not-before 0" in calls[0]
    assert "--resume" in calls[1] and "--broadcast" not in calls[1]


def test_record_only_without_a_broadcast_record_fails(tmp_path):
    log = tmp_path / "calls.log"
    result = _testnet(tmp_path, log, RECORD_ONLY="1", **_dirs(tmp_path, PLACEHOLDER, with_broadcast=False))
    assert result.returncode == 1
    assert "no broadcast record" in result.stderr
    assert _calls(log) == []


def test_redeploy_flag_allows_a_new_deployment(tmp_path):
    log = tmp_path / "calls.log"
    result = _testnet(tmp_path, log, REDEPLOY="1", **_dirs(tmp_path, DEPLOYED, with_broadcast=True))
    assert result.returncode == 0, result.stderr
    assert [c.split()[0] for c in _calls(log)] == ["uv", "forge", "uv", "forge"]


def test_local_deploy_never_verifies(tmp_path):
    log = tmp_path / "calls.log"
    result = _run("local", ENV_FILE=str(_env_file(tmp_path)), GIT=str(_clean_git(tmp_path)),
                  FORGE=str(_logging_stub(tmp_path, "forge", log)), UV=str(_logging_stub(tmp_path, "uv", log)))
    assert result.returncode == 0, result.stderr
    calls = _calls(log)
    assert [c.split()[0] for c in calls] == ["forge", "uv"]
    assert "--verify" not in calls[0]
