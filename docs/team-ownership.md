# StressProof — Team Ownership & Integration Contracts

To ensure independent, unblocked velocity across the 40-hour timeline, this document specifies code ownership, review responsibilities, and synchronization gates.

---

## 1. Ownership & Review Matrix

| Component / Subsystem | Primary Owner | Reviewer | Notes |
|---|---|---|---|
| `contracts/` (Solidity) | Developer 3 | Developer 2 | Special review on pull payments and invariants. |
| `core/` (`stressproof_core`) | Developer 2 | Developer 3 | Special review on integer-only division and zero-float rule. |
| `pipeline/` (Aave extraction) | Developer 2 | Developer 3 | Verification of Multicall3 and reserve bit layout. |
| `backend/` (FastAPI) | Developer 2 | Developer 1 | Ensures API response schemas match frontend expectations. |
| `agents/` (Watcher, Attester, CLI) | Developer 3 | Developer 2 | Ensures watcher correctly invokes `stressproof_core.replay`. |
| `frontend/` (Next.js) | Developer 1 | Developer 2 (Hash), Developer 3 (Web3) | In-browser Keccak-256 and contract call UX. |
| `deployments/*.json` | Developer 3 | Developer 1, 2 | Generated on deploy; must never be edited manually. |
| `scripts/export_abis.sh` | Developer 3 | Developer 1 | Exports contract artifacts to frontend and agents. |

---

## 2. Handoff Timeline & Milestones

The following timeline coordinates deliverable milestones across developers:

```
Hour 0 ─── Kickoff & Workspace Scaffolding (All)
Hour 3 ─── B -> A, C: Small Golden Fixture (data/fixtures/casefile_v1.json + hash)
Hour 5 ─── A -> B, C: Freeze IStressRegistry.sol & initial ABIs
Hour 8 ─── A -> All: deployments/31337.json (Local Anvil deployment)
Hour 8 ─── B -> All: Frozen dataset manifest (REAL vs SYNTHETIC decision)
Hour 14 ── B -> A: Parameter sweep result: shockBps & honest bad debt R
Hour 16 ── A -> All: deployments/84532.json (Testnet deployment with real thresholds)
Hour 20 ── B -> C: Live backend running at BACKEND_PUBLIC_URL with live agent feed
Hour 24 ── GATE-24: Full Phase 1 Flow Pass (Local Anvil + Testnet)
           * No Phase 2 work starts until GATE-24 passes!
Hour 34 ── Phase 2 Feature Freeze (TigerGraph & LLM proposals)
Hour 38 ── Rehearsal & Backup Video Recording
Hour 39 ── Total Code Freeze
```

---

## 3. Communication Protocols

* **Schema Changes:** Any change to a schema in `docs/schemas/` or `core/src/stressproof_core/models.py` must be announced immediately with commit prefix `SCHEMA:`.
* **Interface / ABI Changes:** Any change to `contracts/src/IStressRegistry.sol` requires a team sync, commit prefix `ABI:`, and running `make abis`.
