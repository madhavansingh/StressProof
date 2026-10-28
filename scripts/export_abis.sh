#!/usr/bin/env bash
# Export compiled contract ABIs (functions, events and custom errors) for the frontend and agents.
#
# Run `forge build` in contracts/ first. Fails if any artifact is missing or has no ABI.
# Output folders can be overridden, e.g. to check the export without touching the repo:
#   ABI_OUT_FRONTEND=/tmp/abi ABI_OUT_AGENTS=/tmp/abi bash scripts/export_abis.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACTS_DIR="$REPO_ROOT/contracts/out"
ABI_OUT_FRONTEND="${ABI_OUT_FRONTEND:-$REPO_ROOT/frontend/src/abi}"
ABI_OUT_AGENTS="${ABI_OUT_AGENTS:-$REPO_ROOT/agents/src/stressproof_agents/abi}"
CONTRACTS=(StressRegistry DemoVault MockLendingMarket IStressRegistry)

echo "==> Exporting contract ABIs"

if [ ! -d "$ARTIFACTS_DIR" ]; then
    echo "ERROR: $ARTIFACTS_DIR not found. Run 'forge build' in contracts/ first." >&2
    exit 1
fi

# Use the first Python that actually runs: an Intel-only python3 on an Apple Silicon Mac
# without Rosetta is on PATH but fails with "Bad CPU type".
PYTHON_BIN=""
for candidate in "${PYTHON:-}" python3 /usr/bin/python3; do
    if [ -n "$candidate" ] && "$candidate" -c "" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: no working python3 found. Set PYTHON=/path/to/python3." >&2
    exit 1
fi

mkdir -p "$ABI_OUT_FRONTEND" "$ABI_OUT_AGENTS"

for contract in "${CONTRACTS[@]}"; do
    artifact="$ARTIFACTS_DIR/${contract}.sol/${contract}.json"
    if [ ! -f "$artifact" ]; then
        echo "ERROR: missing artifact $artifact. Run 'forge build' in contracts/." >&2
        exit 1
    fi
    # Paths are passed as arguments, never pasted into the Python source.
    "$PYTHON_BIN" - "$artifact" "$ABI_OUT_FRONTEND/${contract}.json" "$ABI_OUT_AGENTS/${contract}.json" <<'PY'
import json
import sys

artifact, *outputs = sys.argv[1:]
with open(artifact, encoding="utf-8") as f:
    abi = json.load(f).get("abi")
if not abi:
    sys.exit(f"ERROR: no ABI in {artifact}")

text = json.dumps(abi, indent=2) + "\n"
for path in outputs:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

kinds = {}
for entry in abi:
    kinds[entry["type"]] = kinds.get(entry["type"], 0) + 1
summary = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
print(f"    {artifact.rsplit('/', 1)[-1]}: {summary}")
PY
done

echo "==> Wrote ABIs to:"
echo "    $ABI_OUT_FRONTEND"
echo "    $ABI_OUT_AGENTS"
