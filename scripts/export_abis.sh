#!/usr/bin/env bash
set -euo pipefail

echo "==> Exporting smart contract ABIs to frontend and agents..."

ABI_OUT_FRONTEND="frontend/src/abi"
ABI_OUT_AGENTS="agents/src/stressproof_agents/abi"

mkdir -p "$ABI_OUT_FRONTEND"
mkdir -p "$ABI_OUT_AGENTS"

# If forge has built contracts/out, copy artifacts
if [ -d "contracts/out" ]; then
    for contract in StressRegistry DemoVault MockLendingMarket IStressRegistry; do
        if [ -f "contracts/out/${contract}.sol/${contract}.json" ]; then
            python3 -c "import json; f=open('contracts/out/${contract}.sol/${contract}.json'); d=json.load(f); open('${ABI_OUT_FRONTEND}/${contract}.json', 'w').write(json.dumps(d.get('abi', []), indent=2)); open('${ABI_OUT_AGENTS}/${contract}.json', 'w').write(json.dumps(d.get('abi', []), indent=2))"
            echo "Exported ABI for ${contract}"
        fi
    done
else
    echo "Notice: contracts/out does not exist yet. Run 'forge build' first."
fi

echo "==> ABI export complete."
