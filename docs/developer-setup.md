# StressProof — Developer Setup Guide

This guide details how each of the three developers sets up their local environment and runs their respective components.

---

## Prerequisites (All Developers)

* **macOS or Linux**
* **Git**
* **Node.js LTS (v20+)** and **pnpm** (`npm install -g pnpm`)
* **Python 3.11+**
* **uv** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
* **Foundry** (`curl -L https://foundry.paradigm.xyz | bash && foundryup`)

---

## 1. Developer 1 — Frontend Setup

Developer 1 owns `frontend/`.

```bash
# 1. Install frontend dependencies
cd frontend
pnpm install

# 2. Configure environment
cp ../.env.example .env.local
# Set NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
# Set NEXT_PUBLIC_CHAIN_ID=31337 (or 84532)

# 3. Start development server
pnpm dev

# 4. Run tests
pnpm test
```

### Mocking & Running Independent of Backend/Contracts:
* The frontend consumes `deployments/31337.json` for contract addresses.
* Fixtures in `data/fixtures/casefile_v1.json` allow in-browser hash testing (`lib/verify.ts`) without a running backend.

---

## 2. Developer 2 — Backend & Risk Engine Setup

Developer 2 owns `core/`, `pipeline/`, and `backend/`.

```bash
# 1. Sync Python workspace
uv sync

# 2. Run pure core tests (Appendix A test vectors & property tests)
uv run pytest core/tests

# 3. Start FastAPI backend
make backend
# Server runs on http://127.0.0.1:8000
# OpenAPI documentation available at http://127.0.0.1:8000/docs
```

### Snapshot Extraction (Pipeline):
```bash
# Extract Aave v3 positions using Anvil fork:
export MAINNET_ARCHIVE_RPC_URL="https://eth-mainnet.alchemy.com/v2/YOUR_KEY"
export FORK_BLOCK=19000000
make fork          # in terminal 1
make pin           # in terminal 2
make extract
make normalize
make sweep
```

---

## 3. Developer 3 — Blockchain & Agents Setup

Developer 3 owns `contracts/` and `agents/`.

```bash
# 1. Test smart contracts
cd contracts
forge test

# 2. Start local Anvil testnet (separate standalone node on 8546)
make chain

# 3. Deploy contracts to local node
make deploy-local

# 4. Export compiled ABIs to frontend and agents
make abis

# 5. Run Watcher agent daemon
make watcher

# 6. Publish an honest test claim
make attest

# 7. Publish an inflated claim for dispute testing
make evil

# 8. Resolve dispute via CLI
make resolve ID=1
```

---

## 4. Full Integration (E2E)

To verify all components interacting together locally:
```bash
make e2e
```
This executes `scripts/e2e_local.sh`, running local anvil, deploying contracts, running backend, watcher, attester, and resolver through both the honest and disputed paths.
