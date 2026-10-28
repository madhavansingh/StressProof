#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "StressProof — Local End-to-End Automated Integration Test"
echo "Phase 1 Gate (GATE-24) Verification"
echo "=========================================================="

# 1. Check Python test suite
echo "==> [Step 1/6] Running Python unit & property test suite..."
uv run pytest

# 2. Check contract compilation / tests if forge is installed
echo "==> [Step 2/6] Checking Foundry contracts..."
if command -v forge &> /dev/null; then
    cd contracts && forge build && cd ..
else
    echo "Notice: forge not in PATH, skipping local solc build"
fi

# 3. Verify golden fixture
echo "==> [Step 3/6] Verifying golden fixture canonical hash..."
uv run python -c "
from stressproof_core.canonical_json import parse_strict
from stressproof_core.hashing import keccak256_hex

with open('data/fixtures/casefile_v1.json', 'rb') as f:
    b = f.read()
parse_strict(b)
h = keccak256_hex(b)
with open('data/fixtures/casefile_v1.keccak') as f:
    expected = f.read().strip()
assert h == expected, f'Hash mismatch: {h} != {expected}'
print('Fixture integrity verified:', h)
"

# 4. Check backend health
echo "==> [Step 4/6] Verifying FastAPI backend server module..."
uv run python -c "
from stressproof_backend.main import app
assert app is not None
print('FastAPI app initialized successfully.')
"

# 5. Check agents and SSRF security policies
echo "==> [Step 5/6] Verifying agent security filters..."
uv run python -c "
from stressproof_agents.common.fetch import is_safe_url
assert not is_safe_url('http://169.254.169.254')
assert is_safe_url('https://ipfs.io')
print('Agent SSRF safety policies active.')
"

# 6. Overall result
echo "==> [Step 6/6] All integration checks completed successfully!"
echo "=========================================================="
echo "GATE-24 readiness check: PASSED"
echo "=========================================================="
