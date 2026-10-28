# StressProof — Contributing & Multi-Developer Guidelines

Welcome to the StressProof engineering team! This monorepo is engineered to allow three developers to build in parallel across frontend, backend/risk-engine, and blockchain/agents without blocking each other.

---

## 1. Team Ownership & Responsibilities

| Role | Domain / Packages | Primary Responsibilities |
|---|---|---|
| **Developer 1 (Frontend)** | `frontend/` | Next.js App Router, Tailwind/shadcn UI, Wagmi/Viem wallet integration, in-browser hash verification, reactive claims list, interactive borrowing demo. |
| **Developer 2 (Backend & Risk Engine)** | `core/`, `pipeline/`, `backend/` | Pure Python `static-liquidation-v1` deterministic replayer, canonical JSON serializer, Keccak hashing, validation rules V-01..V-14, Aave v3 extraction, FastAPI content-addressed storage, agent feed. |
| **Developer 3 (Blockchain & AI)** | `contracts/`, `agents/` | Solidity smart contracts (`StressRegistry`, `DemoVault`, `MockLendingMarket`), Foundry test suite, bond accounting invariants, autonomous agents (attester, watcher, resolver CLI, malicious attester), Phase 2 TigerGraph & LLM. |

---

## 2. Monorepo Principles & Boundaries

1. **Isolation of the Verdict Path:**
   * The on-chain claim resolution depends **strictly** on deterministic replay: `canonical_bytes` $\rightarrow$ `keccak256` $\rightarrow$ validation rules V-01..V-14 $\rightarrow$ `static-liquidation-v1` integer math.
   * Neither the AI (LLM) nor the TigerGraph exposure graph may ever enter the verdict path. AI proposes scenarios; deterministic code re-executes and verifies them.
2. **Pure Core Engine:**
   * `stressproof_core` must never perform network I/O, file system operations, or clock/randomness checks. It is imported by `backend/`, `pipeline/`, and `agents/`.
3. **Integer Arithmetic Discipline:**
   * Never use floats, `math.floor()`, or decimals in replay calculations. Use integer floor division `//` on non-negative integers only.
4. **Raw Bytes Integrity:**
   * Transport is untrusted. Verification relies strictly on hashing raw retrieved bytes (`keccak256(rawBytes) == evidenceHash`). Never re-serialize JSON before hashing.
5. **Contract Pull Payments:**
   * All bond payouts and refunds credit an internal `credits[address]` ledger. Users and agents withdraw their balance explicitly via `withdraw()`.

---

## 3. Branching, Commits, and Pull Requests

* **Branch Naming:**
  * `feat/frontend-<feature>`
  * `feat/core-<feature>`
  * `feat/contracts-<feature>`
  * `feat/agents-<feature>`
  * `fix/<issue>`
* **Handoff Notifications:**
  * When modifying shared data schemas in `docs/schemas/` or `core/src/stressproof_core/models.py`, prefix commit messages with `SCHEMA:`.
  * When modifying smart contract interfaces in `contracts/src/IStressRegistry.sol`, prefix commit messages with `ABI:` and immediately run `make abis`.

---

## 4. Testing & Verification Requirements

Before submitting a PR or merging to `main`:
1. **Contract Tests:** `cd contracts && forge test` (must pass all unit tests and `Invariant.t.sol`).
2. **Python Tests:** `uv run pytest` (must pass all property tests and test vectors from Appendix A).
3. **Frontend Tests:** `cd frontend && pnpm test`.
4. **Integration Gate:** `make e2e` must pass on local Anvil.
