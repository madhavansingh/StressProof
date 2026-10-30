#!/usr/bin/env bash
# Socket supply-chain scan of StressProof's dependency lockfiles (WP-1; implementation plan S-13).
#
# What Socket scans here: frontend/package.json + frontend/package-lock.json (npm) and the uv workspace
# (pyproject.toml files + uv.lock, PyPI). Not covered by Socket: Foundry's forge-std, a git submodule
# under contracts/lib (excluded below; Socket's supported-file list has no submodule support).
#
# Requirements: a Socket API token (the free plan includes one) with the scopes full-scans:create,
# full-scans:list and security-policy:read, exported as SOCKET_CLI_API_TOKEN (or the legacy
# SOCKET_SECURITY_API_TOKEN). The token is read from the environment only; it is never passed on a
# command line or printed.
#
# Output: the JSON scan report in ${SOCKET_REPORT_DIR:-socket-report}/socket-scan.json (git-ignored).
# Exit codes: 0 scan created and reported; 2 not run (no token); otherwise the Socket CLI's failure.
# The pinned CLI documents no exit code for policy alerts; confirm that behaviour on the first real run.
#
# Overrides: NPX, GIT (tool paths), SOCKET_CLI_VERSION, SOCKET_REPO, SOCKET_REPORT_DIR,
# SOCKET_READ_ONLY=1 (reads remote state, creates no scan or report).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Pinned to a release older than two weeks at the time it was chosen (1.8.3, 2026-10-15).
SOCKET_CLI_VERSION="${SOCKET_CLI_VERSION:-1.8.3}"
NPX="${NPX:-npx}"
GIT="${GIT:-git}"
REPO_NAME="${SOCKET_REPO:-StressProof}"
REPORT_DIR="${SOCKET_REPORT_DIR:-$REPO_ROOT/socket-report}"

token="${SOCKET_CLI_API_TOKEN:-${SOCKET_SECURITY_API_TOKEN:-}}"
if [ -z "$token" ]; then
    {
        echo "Socket scan NOT RUN: no Socket API token in SOCKET_CLI_API_TOKEN or SOCKET_SECURITY_API_TOKEN."
        echo "Create one at https://socket.dev (the free plan includes one API token) with the scopes"
        echo "full-scans:create, full-scans:list and security-policy:read, then export it and re-run."
    } >&2
    exit 2
fi
export SOCKET_CLI_API_TOKEN="$token"
unset token

cd "$REPO_ROOT"
branch="$("$GIT" rev-parse --abbrev-ref HEAD)"
commit="$("$GIT" rev-parse HEAD)"
mkdir -p "$REPORT_DIR"

# Socket uploads the manifests on disk but labels the scan with HEAD. Say so when they differ.
dirty_manifests="$("$GIT" status --porcelain -- uv.lock pyproject.toml '*/pyproject.toml' frontend/package.json frontend/package-lock.json 2>/dev/null || true)"
if [ -n "$dirty_manifests" ]; then
    {
        echo "WARNING: scanning uncommitted manifest changes; the scan is labelled ${commit:0:12} but uses the files on disk:"
        echo "$dirty_manifests"
    } >&2
fi

args=(--yes "socket@${SOCKET_CLI_VERSION}" scan create
    --no-interactive
    --repo "$REPO_NAME"
    --branch "$branch"
    --commit-hash "$commit"
    --exclude-paths contracts/lib
    --json)
if [ "${SOCKET_READ_ONLY:-0}" = 1 ]; then
    args+=(--read-only)
else
    # Include warn-level policy alerts, not only errors (the CLI default for scan create is 'error').
    args+=(--report --report-level warn)
fi

echo "==> Socket scan (CLI socket@${SOCKET_CLI_VERSION}) of ${REPO_NAME}@${branch} ${commit:0:12}"
set +e
"$NPX" "${args[@]}" . >"$REPORT_DIR/socket-scan.json"
status=$?
set -e

if [ "$status" -ne 0 ]; then
    echo "Socket scan FAILED (exit ${status}); see ${REPORT_DIR}/socket-scan.json." >&2
    exit "$status"
fi
echo "==> Socket scan report written to ${REPORT_DIR}/socket-scan.json"
