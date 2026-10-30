# StressProof — Submission

**Track:** AI x Crypto. **Owner:** single project owner (see `CONTRIBUTING.md`, Governance).
**Date:** 2026-10-30. **Branch:** `blockchain`.

## One paragraph

StressProof makes AI-generated lending-market risk claims accountable. An attester publishes a stress-test
result ("−30% WETH leaves $2,000 of residual bad debt") on chain with a 0.01 ETH bond and the keccak-256 hash of
a case file. Anyone can fetch the file, check the hash and re-run the deterministic, integer-only replay. A
wrong claim is challenged and loses its bond. A claim that survives finalizes and can tighten a connected
vault's risk controls: max LTV 80% → 50%, or a borrow pause. The verdict is always the deterministic replay;
the AI, the graph and the UI never decide a dispute.

## Where to look

| For | Read |
|---|---|
| Overview, setup, test results, limitations | [README.md](../README.md) |
| Architecture and trust boundaries | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Exact demo sequence and commands | [DEMO_GUIDE.md](DEMO_GUIDE.md) |
| Full original specification | [implementationplan.md](implementationplan.md) |
| Protocol design & bonding | [PROTOCOL_DESIGN.md](PROTOCOL_DESIGN.md) |
| Cryptographic evidence & replayer | [CRYPTOGRAPHIC_EVIDENCE.md](CRYPTOGRAPHIC_EVIDENCE.md) |
| Security model & threat matrix | [SECURITY_MODEL.md](SECURITY_MODEL.md) |
| Repository module structure | [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md) |
| Local development & setup | [DEVELOPMENT.md](DEVELOPMENT.md) |
| End-to-end data flow | [DATA_FLOW.md](DATA_FLOW.md) |
| Phase 2 work packages and their status | [phase2_execution_plan.md](phase2_execution_plan.md) |
| Why Phase 2 started while GATE-24 is pending | [phase2_gate_amendment.md](phase2_gate_amendment.md) |
| API endpoints | [../backend/README.md](../backend/README.md), [integration-contracts.md](integration-contracts.md) |

## Delivered

| Component | Status | Evidence |
|---|---|---|
| `StressRegistry`, `DemoVault`, `MockLendingMarket` (Solidity) | Implemented, locally deployed | `forge test`: 95 passed, including invariant tests |
| Deterministic replay `static-liquidation-v1`, case-file validation (Python) | Implemented | Golden fixture `data/fixtures/casefile_v1.*`; Python suite 770 passed |
| FastAPI backend (stress runs, case files, replay reports, replay outputs, feed) | Implemented | Backend tests; filesystem and Postgres storage |
| Agents: attester, watcher, resolver CLI, malicious attester | Implemented | Agent tests; GATE-24 local run |
| Frontend: landing, dashboard, stress, claims, vault, feed, graph | Implemented | vitest 230 passed; production build passes; UI lifecycle check on 2026-10-30 (injected test wallet) |
| WP-1 Socket supply-chain scan and triage | Complete | README "Supply-chain scan (Socket)"; `scripts/socket_scan.sh`; CI workflow |
| WP-2..5 TigerGraph | Schema created in Savanna; CSV loading pending; no live data connected | `tigergraph/`, `backend/tests/test_tigergraph.py` (fake TigerGraph) |
| WP-6 Interactive graph from replay outputs | Complete (local), operational | `/graph`; `GET /replay-outputs/{hash}`; 53 graph tests |
| WP-13 Wallet-signed transaction UX and fixes | Complete locally with an injected test wallet | `docs/phase2_execution_plan.md` §4; MetaMask manual check by the owner |
| Single-owner governance, conditional Phase 2 | Recorded | `CONTRIBUTING.md`, `docs/phase2_gate_amendment.md` |

## Verification status

| Item | Status |
|---|---|
| GATE-24 local checks | **Passed 101/101** |
| Full lifecycle on local Anvil (publish, challenge, resolve, finalize, expire, apply, borrow check, withdraw) | **Verified locally** |
| Same flows signed with the MetaMask extension | Owner's manual check (`DEMO_GUIDE.md` §5–§10) |
| Base Sepolia deployment | **Pending** (`deployments/84532.json` holds zero addresses; wallets not funded) |
| GATE-24 testnet steps 3–7 | **Pending** |
| Final release | Blocked until GATE-24 passes on testnet |

## Mocked or synthetic (by design, and labelled in the app)

- Dataset `weth-stable-fixture-v1`: 6 **SYNTHETIC** accounts. The real-data pipeline exists; no real snapshot ships.
- Lending market: `MockLendingMarket`.
- Demo timing and thresholds: 120 s challenge window, 300 s resolution window, $1,000 and $4,000 vault
  thresholds, chosen so effects are visible.
- One designated, trusted resolver key.

## Not implemented

- LLM scenario proposer (WP-7). The attester uses a fixed −3000 bps scenario.
- Live TigerGraph data. TigerGraph schema created successfully in Savanna (5 vertex types, 6 edge types, by the project owner); CSV data loading **pending**; no live TigerGraph data is connected to the app. The synthetic graph visualization (local deterministic replay) is operational. The loader, reconciler, query, endpoint and UI panel are built and tested against a fake TigerGraph (`tigergraph/README.md`).
- Next.js 15.5.28+ migration (open security task; see below).

## Security notes

- No `.env` files, keys or tokens are tracked; `.env.example` files hold placeholders only. The Socket token is
  read from the environment and never printed or committed; scan reports (`socket-report/`) are git-ignored.
- Wallet writes are chain-guarded: wrong network refused before signing, and challenge, finalize and expire
  simulated first.
- **Known open issue:** `next` 14.2.35 has unpatched advisories. The two Image Optimization RCEs are unreachable
  (`images.unoptimized: true`, verified); the App Router Server Component denial-of-service and cache-poisoning
  advisories remain until the Next.js migration. This is **not fixed**.

## Submission checklist

- [x] README explains the problem, protocol, architecture, setup, tests and limitations
- [x] Demo guide with exact commands (`docs/DEMO_GUIDE.md`)
- [x] Architecture document with trust boundaries (`docs/ARCHITECTURE.md`)
- [x] All suites pass locally (forge 95, pytest 770 + 73 skipped, vitest 230, tsc clean, production build)
- [x] SYNTHETIC data labelled in the app and in the docs
- [x] Testnet status stated as pending everywhere
- [x] No secrets tracked
- [ ] Owner: MetaMask walk-through of `DEMO_GUIDE.md` §5–§10
- [ ] Owner: commit and push (the CI Socket workflow then re-scans the committed lockfiles)
- [ ] After submission: fund wallets, `ENV_FILE=.env.testnet make deploy-testnet`, GATE-24 steps 3–7
