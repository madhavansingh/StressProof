"""Tests for scripts/socket_scan.sh (WP-1). `npx` is replaced by a stub: nothing is downloaded and no
Socket API is contacted. The token must never appear on a command line or in output."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "socket_scan.sh"
FAKE_TOKEN = "sktsec_TESTONLY_not_a_real_token_0123456789"


def _stub_npx(tmp_path: Path, exit_code: int = 0) -> tuple[Path, Path]:
    log = tmp_path / "npx.log"
    stub = tmp_path / "npx"
    stub.write_text(
        "#!/bin/sh\n"
        f'echo "ARGS $*" >> "{log}"\n'
        f'if [ -n "$SOCKET_CLI_API_TOKEN" ]; then echo "TOKEN_IN_ENV yes" >> "{log}"; fi\n'
        'echo \'{"ok": true, "data": {"healthy": true}}\'\n'
        f"exit {exit_code}\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub, log


def _git_stub(tmp_path: Path, dirty: str = "") -> Path:
    stub = tmp_path / "git"
    stub.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  *--abbrev-ref*) echo blockchain ;;\n'
        "  *rev-parse*) echo 0123456789abcdef0123456789abcdef01234567 ;;\n"
        f"  *status*) printf '%s' '{dirty}' ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def _run(tmp_path: Path, dirty: str = "", **env: str) -> subprocess.CompletedProcess:
    base = {k: v for k, v in os.environ.items() if not k.startswith("SOCKET_")}
    base.update({"SOCKET_REPORT_DIR": str(tmp_path / "report"), "GIT": str(_git_stub(tmp_path, dirty))})
    base.update(env)
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=base, timeout=60)


def test_without_a_token_the_scan_is_reported_as_not_run(tmp_path):
    npx, log = _stub_npx(tmp_path)
    result = _run(tmp_path, NPX=str(npx))
    assert result.returncode == 2
    assert "Socket scan NOT RUN" in result.stderr
    assert "full-scans:create" in result.stderr
    assert not log.exists()


def test_runs_the_pinned_cli_on_the_repo_with_the_token_only_in_the_environment(tmp_path):
    npx, log = _stub_npx(tmp_path)
    result = _run(tmp_path, NPX=str(npx), SOCKET_CLI_API_TOKEN=FAKE_TOKEN)
    assert result.returncode == 0, result.stderr
    calls = log.read_text()
    assert "socket@1.8.3 scan create" in calls
    for flag in ("--no-interactive", "--report", "--json", "--repo StressProof", "--branch blockchain",
                 "--commit-hash 0123456789abcdef0123456789abcdef01234567", "--exclude-paths contracts/lib",
                 "--report-level warn"):
        assert flag in calls, flag
    assert "TOKEN_IN_ENV yes" in calls
    assert FAKE_TOKEN not in calls  # never on the command line
    assert FAKE_TOKEN not in result.stdout + result.stderr
    assert (tmp_path / "report" / "socket-scan.json").read_text().strip().startswith("{")


def test_accepts_the_legacy_token_variable(tmp_path):
    npx, log = _stub_npx(tmp_path)
    result = _run(tmp_path, NPX=str(npx), SOCKET_SECURITY_API_TOKEN=FAKE_TOKEN)
    assert result.returncode == 0, result.stderr
    assert "TOKEN_IN_ENV yes" in log.read_text()


def test_a_failing_scan_fails_the_script(tmp_path):
    npx, _ = _stub_npx(tmp_path, exit_code=1)
    result = _run(tmp_path, NPX=str(npx), SOCKET_CLI_API_TOKEN=FAKE_TOKEN)
    assert result.returncode == 1
    assert "Socket scan FAILED" in result.stderr


def test_read_only_mode_creates_no_report(tmp_path):
    npx, log = _stub_npx(tmp_path)
    result = _run(tmp_path, NPX=str(npx), SOCKET_CLI_API_TOKEN=FAKE_TOKEN, SOCKET_READ_ONLY="1")
    assert result.returncode == 0, result.stderr
    calls = log.read_text()
    assert "--read-only" in calls and "--report" not in calls


def test_warns_when_scanned_manifests_are_not_committed(tmp_path):
    # The scan uploads files from disk but is labelled with HEAD; say so when they differ.
    npx, _ = _stub_npx(tmp_path)
    result = _run(tmp_path, dirty=" M frontend/package-lock.json\n", NPX=str(npx), SOCKET_CLI_API_TOKEN=FAKE_TOKEN)
    assert result.returncode == 0, result.stderr
    assert "uncommitted" in result.stderr and "frontend/package-lock.json" in result.stderr


def test_no_warning_when_manifests_are_committed(tmp_path):
    npx, _ = _stub_npx(tmp_path)
    result = _run(tmp_path, NPX=str(npx), SOCKET_CLI_API_TOKEN=FAKE_TOKEN)
    assert result.returncode == 0, result.stderr
    assert "uncommitted" not in result.stderr
