#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "StressProof — Demo Day Walkthrough Script"
echo "Matches StressProof_Final.md §11"
echo "=========================================================="

echo "Step 1: Verify all 5 wallets funded"
echo "Step 2: Start watcher daemon: make watcher"
echo "Step 3: Honest claim publication: make attest"
echo "Step 4: Watcher verifies and confirms MATCH (no challenge)"
echo "Step 5: Finalize and apply to DemoVault: borrow paused or LTV reduced"
echo "Step 6: Dishonest claim publication: make evil"
echo "Step 7: Watcher detects discrepancy and challenges: WRONG_RESULT"
echo "Step 8: Resolver CLI verifies and upholds challenge: make resolve ID=<id>"
echo "Step 9: Watcher claims slashed bond: +0.01 ETH reward"
echo "Step 10: Slashed claim rejected by DemoVault"
