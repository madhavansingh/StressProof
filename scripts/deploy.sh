#!/usr/bin/env bash
# Deploy StressRegistry, DemoVault and MockLendingMarket, then write deployments/<chainId>.json
# from the confirmed receipts.
#
# Usage: scripts/deploy.sh local|testnet
#   local    LOCAL_RPC_URL (default http://127.0.0.1:8546), chain 31337; warns about uncommitted changes
#   testnet  TESTNET_RPC_URL, chain 84532; refuses uncommitted changes; verifies sources on the explorer
#
# The deployments file is replaced only if `forge script --broadcast` succeeds AND
# scripts/write_deployment.py confirms every receipt and on-chain value. A dry run, a failed
# broadcast or a failed check leaves any existing deployments file untouched.
#
# Overrides: FORGE, GIT, UV (tool paths) and ENV_FILE (default .env).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORGE="${FORGE:-forge}"
GIT="${GIT:-git}"
UV="${UV:-uv}"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"

die() {
    echo "ERROR: $*" >&2
    echo "Deployments file NOT written." >&2
    exit 1
}

target="${1:-}"
case "$target" in
    local) chain_id=31337 ;;
    testnet) chain_id=84532 ;;
    *)
        echo "Usage: $0 local|testnet" >&2
        exit 2
        ;;
esac

cd "$REPO_ROOT"
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found (copy .env.example and fill it in)"
dirty="$("$GIT" status --porcelain)" || die "git status failed (set GIT=/path/to/git)"
commit="$("$GIT" rev-parse HEAD)" || die "git rev-parse failed"

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
export GIT_COMMIT="$commit"

verify_flag=""
if [ "$target" = "local" ]; then
    rpc_url="${LOCAL_RPC_URL:-http://127.0.0.1:8546}"
    [ -z "$dirty" ] || echo "WARNING: uncommitted changes; gitCommit will not describe the deployed code" >&2
else
    rpc_url="${TESTNET_RPC_URL:-}"
    [ -n "$rpc_url" ] || die "TESTNET_RPC_URL is not set"
    [ -z "$dirty" ] || die "commit first; testnet deploys must match a commit"
    verify_flag="--verify"
fi
[ -n "${MARKET_ID_STRING:-}" ] || die "MARKET_ID_STRING is not set"

out_file="deployments/${chain_id}.json"
broadcast_file="contracts/broadcast/Deploy.s.sol/${chain_id}/run-latest.json"
started_at="$(date +%s)"

# The RPC URL is never echoed: provider URLs often contain API keys.
echo "==> Deploying to chain ${chain_id} (commit ${commit})"
(cd contracts && "$FORGE" script script/Deploy.s.sol:Deploy --rpc-url "$rpc_url" --broadcast $verify_flag) \
    || die "forge script failed"

echo "==> Writing ${out_file} from confirmed receipts"
DEPLOY_RPC_URL="$rpc_url" "$UV" run --no-sync python scripts/write_deployment.py \
    --broadcast-file "$broadcast_file" \
    --chain-id "$chain_id" \
    --market-id-string "$MARKET_ID_STRING" \
    --git-commit "$commit" \
    --not-before "$started_at" \
    --out "$out_file" \
    || die "deployment could not be confirmed"
