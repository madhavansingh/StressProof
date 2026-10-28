# stressproof-pipeline

Snapshot extraction and normalization pipeline for Aave v3 Ethereum Mainnet positions.

## Overview
1. `pin.py`: Step 1 — Reads block N from Ethereum archive, resolves Pool/Oracle addresses, defines stablecoin allowlist, and generates draft manifest.
2. `extract.py`: Step 2 — Collects borrower addresses from `Borrow(onBehalfOf)` logs and multicall-classifies them on an Anvil fork at block N.
3. `synth.py`: Step 3 — (Optional) Generates deterministic synthetic borrower positions.
4. `normalize.py`: Step 4 — Normalizes, sorts, canonicalizes, and computes `snapshotHash`.
5. `sweep.py`: Runs a shock sweep over `[-1000, ..., -9000]` bps to pick an honest non-zero residual bad debt R and establish thresholds.
