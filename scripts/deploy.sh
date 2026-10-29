#!/usr/bin/env bash
# Deploy StressRegistry, DemoVault and MockLendingMarket, then write deployments/<chainId>.json
# from the confirmed receipts.
#
# Usage: scripts/deploy.sh local|testnet
#   local    LOCAL_RPC_URL (default http://127.0.0.1:8546), chain 31337; warns about uncommitted changes
#   testnet  TESTNET_RPC_URL, chain 84532; reads .env.testnet by default (never the local .env);
#            refuses uncommitted changes; runs scripts/testnet_preflight.py (role keys must be
#            dedicated, distinct and not public development accounts) before broadcasting;
#            verifies sources on the explorer
#
# The deployments file is replaced only if `forge script --broadcast` succeeds AND
# scripts/write_deployment.py confirms every receipt and on-chain value. A dry run, a failed
# broadcast or a failed check leaves any existing deployments file untouched.
#
# Explorer verification (testnet) runs only after the deployments file is written, as
# `forge script --resume --verify` against the same broadcast record; it sends no transactions
# because every one already has a confirmed receipt. Its failure is a warning: live contracts are
# never left unrecorded because verification failed (for example, no explorer API key).
#
# No silent duplicate deployments (testnet): the script refuses to broadcast when
# deployments/84532.json already records a deployment, or when a broadcast record exists that was
# never recorded (a deploy whose recording failed). RECORD_ONLY=1 records that existing broadcast
# without sending anything (run it from the same commit); REDEPLOY=1 deploys a new set on purpose.
#
# Overrides: FORGE, GIT, UV (tool paths), ENV_FILE (default .env, or .env.testnet for testnet), DEPLOYMENTS_DIR and
# BROADCAST_DIR (tests), RECORD_ONLY, REDEPLOY.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORGE="${FORGE:-forge}"
GIT="${GIT:-git}"
UV="${UV:-uv}"

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

# Testnet keys live in their own git-ignored file, so a testnet deploy never picks up the local
# Anvil keys from .env by accident.
if [ -z "${ENV_FILE:-}" ]; then
    if [ "$target" = "testnet" ]; then ENV_FILE="$REPO_ROOT/.env.testnet"; else ENV_FILE="$REPO_ROOT/.env"; fi
fi

cd "$REPO_ROOT"
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found (copy .env.example and fill it in)"
dirty="$("$GIT" status --porcelain)" || die "git status failed (set GIT=/path/to/git)"
commit="$("$GIT" rev-parse HEAD)" || die "git rev-parse failed"

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
export GIT_COMMIT="$commit"

verify_after=0
if [ "$target" = "local" ]; then
    rpc_url="${LOCAL_RPC_URL:-http://127.0.0.1:8546}"
    [ -z "$dirty" ] || echo "WARNING: uncommitted changes; gitCommit will not describe the deployed code" >&2
else
    rpc_url="${TESTNET_RPC_URL:-}"
    [ -n "$rpc_url" ] || die "TESTNET_RPC_URL is not set"
    [ -z "$dirty" ] || die "commit first; testnet deploys must match a commit"
    verify_after=1
fi
[ -n "${MARKET_ID_STRING:-}" ] || die "MARKET_ID_STRING is not set"

out_file="${DEPLOYMENTS_DIR:-deployments}/${chain_id}.json"
broadcast_file="${BROADCAST_DIR:-contracts/broadcast/Deploy.s.sol}/${chain_id}/run-latest.json"
record_only="${RECORD_ONLY:-0}"
started_at="$(date +%s)"

if [ "$record_only" = 1 ]; then
    [ -f "$broadcast_file" ] || die "RECORD_ONLY=1 but there is no broadcast record at ${broadcast_file}"
elif [ "$target" = "testnet" ] && [ "${REDEPLOY:-0}" != 1 ]; then
    if [ -f "$out_file" ] && ! grep -Eq '"registry"[[:space:]]*:[[:space:]]*"0x0{40}"' "$out_file"; then
        die "${out_file} already records a deployment; set REDEPLOY=1 to deploy a new set of contracts on purpose"
    fi
    if [ -f "$broadcast_file" ]; then
        die "an unrecorded broadcast exists at ${broadcast_file}; record it with RECORD_ONLY=1 instead of deploying again (or set REDEPLOY=1)"
    fi
fi

if [ "$target" = "testnet" ] && [ "$record_only" != 1 ]; then
    echo "==> Testnet preflight (local checks of keys and parameters; no transactions)"
    GIT="$GIT" "$UV" run --no-sync python scripts/testnet_preflight.py --env-file "$ENV_FILE" --keys-only \
        || die "testnet preflight failed; fix every FAIL above before deploying"
fi

if [ "$record_only" = 1 ]; then
    echo "==> Recording the existing broadcast for chain ${chain_id} (no transactions sent)"
    started_at=0
else
    # The RPC URL is never echoed: provider URLs often contain API keys.
    echo "==> Deploying to chain ${chain_id} (commit ${commit})"
    (cd contracts && "$FORGE" script script/Deploy.s.sol:Deploy --rpc-url "$rpc_url" --broadcast) \
        || die "forge script failed"
fi

echo "==> Writing ${out_file} from confirmed receipts"
DEPLOY_RPC_URL="$rpc_url" "$UV" run --no-sync python scripts/write_deployment.py \
    --broadcast-file "$broadcast_file" \
    --chain-id "$chain_id" \
    --market-id-string "$MARKET_ID_STRING" \
    --git-commit "$commit" \
    --not-before "$started_at" \
    --out "$out_file" \
    || die "deployment could not be confirmed"

if [ "$verify_after" = 1 ]; then
    echo "==> Verifying sources on the explorer (non-blocking)"
    if ! (cd contracts && "$FORGE" script script/Deploy.s.sol:Deploy --rpc-url "$rpc_url" --resume --verify); then
        echo "WARNING: explorer verification failed; ${out_file} was written and stays valid." >&2
        echo "Retry later with the same environment (set the explorer API key first):" >&2
        echo "  (cd contracts && forge script script/Deploy.s.sol:Deploy --rpc-url \"\$TESTNET_RPC_URL\" --resume --verify)" >&2
    fi
fi
