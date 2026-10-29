# StressProof 

**An open, challengeable layer for AI-generated lending-market risk claims.**

DeFi protocols and DAOs frequently act on risk analyses from closed providers or autonomous agents. **StressProof** makes that analysis accountable: an agent proposes a stress-test claim backed by an on-chain bond and a content-addressed case file. Watcher agents verify the file's hash, re-run deterministic replay from the committed snapshot, and challenge any discrepancies to win the bond. Finalized claims can programmatically trigger on-chain risk controls (e.g. lowering max LTV or pausing borrowing) in a connected vault.

---

## Architecture Overview

```
        Aave v3 Ethereum Mainnet Fork (Pinned Block N)
                       │ extract snapshot
             ┌─────────▼──────────┐
             │  Snapshot Pipeline │
             └─────────┬──────────┘
                       │ canonical snapshot.json
      ┌────────────────▼─────────────────────────────┐
      │              Backend (FastAPI)               │
      │  Core Replayer (static-liquidation-v1)       │
      │  Content-addressed Store (/case-files)       │
      │  Attester Agent ── Watcher Agent ── Resolver │
      └───────────────┬──────────────────────────────┘
                      │ postClaim / challenge / resolve
      ┌───────────────▼──────────────────────────────┐
      │        Smart Contracts (Testnet)             │
      │  StressRegistry ──finalized──► DemoVault     │
      │                                  │           │
      │                          MockLendingMarket   │
      └───────────────────────┬──────────────────────┘
                              │
                     ┌────────▼─────────┐
                     │ Frontend (Next.js)│
                     └──────────────────┘
```

---

## Multi-Developer Quickstart

This monorepo supports concurrent work by three developers:

### 1. Developer 1 — Frontend (`frontend/`)
* **Focus:** Next.js App Router, Tailwind CSS, shadcn/ui, Wagmi/Viem, in-browser hash verification.
* **Setup:**
  ```bash
  cd frontend
  pnpm install
  pnpm dev
  ```
* **Runs against:** Local Anvil (chain 31337 / 8546) or Base Sepolia (chain 84532), interacting with FastAPI backend (`http://localhost:8000`).

### 2. Developer 2 — Backend & Risk Engine (`core/`, `pipeline/`, `backend/`)
* **Focus:** Pure Python `stressproof_core`, Aave v3 pipeline, FastAPI content-addressed storage.
* **Setup:**
  ```bash
  uv sync
  uv run pytest core/tests
  make backend
  ```
* **Core Rule:** `stressproof_core` is pure Python: integer-only math, zero network I/O, no floating-point arithmetic.

### 3. Developer 3 — Blockchain & AI (`contracts/`, `agents/`)
* **Focus:** Solidity smart contracts (`StressRegistry`, `DemoVault`, `MockLendingMarket`), Foundry tests, agent daemons (watcher, attester, resolver CLI).
* **Setup:**
  ```bash
  # Contracts
  cd contracts
  forge test

  # Local Node & Deploy
  make chain
  make deploy-local
  make abis

  # Watcher Daemon
  make watcher
  ```

---

## Repository Map

* `contracts/`: Foundry project with Solidity contracts, deployment scripts, and invariant tests.
* `core/`: Pure Python deterministic calculation library (`stressproof_core`).
* `pipeline/`: Aave v3 borrower discovery and snapshot normalization pipeline.
* `backend/`: FastAPI service managing content-addressed case files, reports, and agent feed.
* `agents/`: Autonomous agent daemons (Attester, Watcher, Resolver CLI, Malicious Attester).
* `frontend/`: Next.js web application with reactive dashboards and wallet integration.
* `deployments/`: Deployed contract addresses and constants per chain ID.
* `data/fixtures/`: Golden fixtures and test vectors used across languages.
* `docs/`: System documentation, architecture specifications, and data schemas.
* `scripts/`: Integration, ABI export, and E2E automation scripts.

---

## Disclosure Statement

> **What StressProof verifies:** that a published case file matches its on-chain hash, and that the claimed residual bad debt is the exact output of the committed snapshot, scenario, and model.
>
> **What it does not verify:** that the snapshot is complete or matches mainnet at the pinned block; that the model is realistic; that data labelled `REAL` truly is (it checks only the declared internal consistency).
>
> **Trusted in this MVP:** a designated resolver; the shared replay code (a bug in it would affect attester and watcher alike); at least one live watcher (unwatched incorrect claims finalize).
>
> **Model:** `static-liquidation-v1` — one liquidation pass, full liquidation, no slippage or price impact, WETH-collateral and stablecoin-debt accounts only, outside eMode. Aave itself liquidates only 50% of debt in some cases. Results are estimates for that subset, not forecasts of Aave losses.
>
> **Staged for the demo:** scripted dishonest attester, designated resolver, mock lending market, 2-minute challenge window, scenario and vault thresholds chosen so the effect is visible.
>
> **Known economic gaps:** fixed bond regardless of impact; a challenge can be front-run by a sock-puppet challenger; finalized claims have no expiry.
