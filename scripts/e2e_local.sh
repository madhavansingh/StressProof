#!/usr/bin/env bash
# GATE-24: the Phase 1 flow end to end on local Anvil (implementationplan.md §21.5, §24).
#
# Documented initial state:
#   - Anvil on 127.0.0.1:8546, chain 31337 (`make chain`, or `anvil --port 8546`)
#   - the contracts from deployments/31337.json deployed there (`make deploy-local`)
#   - .env with the five Anvil test keys (DEPLOYER/ATTESTER/MALICIOUS/WATCHER/RESOLVER_PK) and
#     LOCAL_RPC_URL=http://127.0.0.1:8546; FETCH_ALLOW_LOCALHOST=true
#   - port 8000 free: this script starts its own backend
#
# What it does: starts the backend with all data in a temporary folder, then runs scripts/gate24.py,
# which drives the real attester, malicious-attester, watcher and resolver CLIs through four
# scenarios (honest, malicious, expiry, unsuccessful challenge) and checks every outcome against
# contract reads. The chain is wrapped in evm_snapshot/evm_revert, so it ends where it started;
# the temporary folder is deleted. Nothing outside it is written.
#
# Isolation: the test backend gets DATABASE_URL= (empty), which overrides any value in .env and
# selects filesystem storage under the temporary folder; the run aborts unless /health reports
# "storage": "filesystem". The agents get BACKEND_URL pointing at this local backend, so a deployed
# backend named in .env is never used.
#
# Options: --keep-state (do not revert the chain), --keep-artifacts (keep the temporary folder).
# Exit code 0 only if every check passed.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
BACKEND_URL="http://$BACKEND_HOST:$BACKEND_PORT"
KEEP_ARTIFACTS=0
DRIVER_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --keep-state) DRIVER_ARGS+=("--keep-state") ;;
        --keep-artifacts) KEEP_ARTIFACTS=1 ;;
        *) echo "usage: $0 [--keep-state] [--keep-artifacts]" >&2; exit 2 ;;
    esac
done

cd "$REPO_ROOT"
[ -x "$PYTHON" ] || { echo "ERROR: $PYTHON not found; run 'uv sync' first" >&2; exit 1; }
[ -f .env ] || { echo "ERROR: .env not found (see the initial state above)" >&2; exit 1; }
if "$PYTHON" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('$BACKEND_HOST',$BACKEND_PORT)) else 1)"; then
    : # port free
else
    echo "ERROR: port $BACKEND_PORT is in use; stop the running backend first" >&2
    exit 1
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/stressproof-gate24.XXXXXX")"
BACKEND_PID=""
cleanup() {
    if [ -n "$BACKEND_PID" ]; then kill "$BACKEND_PID" 2>/dev/null || true; wait "$BACKEND_PID" 2>/dev/null || true; fi
    if [ "$KEEP_ARTIFACTS" = 1 ]; then echo "artifacts kept in $WORK_DIR"; else rm -rf "$WORK_DIR"; fi
}
trap cleanup EXIT

echo "==> GATE-24 local run (work dir $WORK_DIR)"
DATABASE_URL= DATA_DIR="$WORK_DIR/backend-data" BACKEND_PUBLIC_URL="$BACKEND_URL" PYTHONDONTWRITEBYTECODE=1 \
    "$PYTHON" -B -m uvicorn stressproof_backend.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
    >"$WORK_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
for _ in $(seq 1 40); do
    if "$PYTHON" -c "import urllib.request; urllib.request.urlopen('http://$BACKEND_HOST:$BACKEND_PORT/datasets', timeout=1)" 2>/dev/null; then
        break
    fi
    kill -0 "$BACKEND_PID" 2>/dev/null || { echo "ERROR: backend exited; see $WORK_DIR/backend.log" >&2; exit 1; }
    sleep 0.5
done
echo "==> backend up on $BACKEND_HOST:$BACKEND_PORT"
# Refuse to send any transaction unless the test backend really uses the temporary filesystem.
STORAGE="$("$PYTHON" -c "import json,urllib.request; print(json.load(urllib.request.urlopen('$BACKEND_URL/health', timeout=5)).get('storage'))")"
if [ "$STORAGE" != "filesystem" ]; then
    echo "ERROR: test backend reports storage '$STORAGE', expected 'filesystem'; aborting before any transaction" >&2
    exit 1
fi
echo "==> backend storage: filesystem ($WORK_DIR/backend-data)"

BACKEND_URL="$BACKEND_URL" BACKEND_PUBLIC_URL="$BACKEND_URL" PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B scripts/gate24.py --work-dir "$WORK_DIR" ${DRIVER_ARGS[@]+"${DRIVER_ARGS[@]}"}
