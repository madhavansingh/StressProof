# StressProof

**An open, challengeable layer for AI-generated lending-market risk claims.**

> **Submission status (2026-10-30).** The full protocol runs and is tested **locally** (Anvil, chain 31337).
> GATE-24 local checks passed **101/101**. **Base Sepolia deployment and testnet acceptance are still pending**
> (wallets not yet funded). All demo data is **SYNTHETIC** (`weth-stable-fixture-v1`, 6 synthetic accounts) and
> does not describe real Aave positions. See [docs/SUBMISSION.md](docs/SUBMISSION.md) for the evaluator overview
> and [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) for the exact demo sequence.

## The problem

Protocols and DAOs act on risk analysis from closed providers and, increasingly, from AI agents. Outsiders
cannot cheaply check that a result is reproducible, and an agent can publish a wrong loss figure at no cost.
A wrong or manipulated result can freeze a market, or leave bad debt unprepared for.

## What StressProof does

An attester publishes a stress-test claim ("a −30% WETH shock leaves $X of residual bad debt in this market")
with a **0.01 ETH bond** and the keccak-256 hash of a **case file** containing the snapshot, scenario, model id
and results. Anyone can fetch the case file, check its hash, and **re-run the deterministic replay**. A wrong
claim can be challenged; the winner of the dispute takes both bonds. A claim that survives the challenge window
finalizes and can **tighten an on-chain risk control** (lower max LTV, or pause borrowing) in a connected vault.

## How the protocol works

1. **Snapshot.** `pipeline/` extracts WETH-collateral, stablecoin-debt Aave v3 borrowers from a mainnet fork at a
   pinned block into a canonical, hashed snapshot. The demo uses a committed SYNTHETIC fixture instead.
2. **Replay.** `core/` (`stressproof_core`, model `static-liquidation-v1`) applies the price shock and computes
   liquidatable accounts, liquidation volume, debt at risk and residual bad debt with integer-only math and no
   network I/O. Same inputs, same bytes, every time.
3. **Evidence.** The backend builds a canonical case file. Its keccak-256 hash is the `evidenceHash`; the file is
   served unchanged at `GET /case-files/{evidenceHash}`. Per-account outputs are stored as derived data.
4. **Bonded claim.** `StressRegistry.postClaim` records the `evidenceHash`, claimed residual bad debt and case-file
   URI with a 0.01 ETH bond, and opens a **120 s challenge window**.
5. **Watch and challenge.** The watcher agent fetches the case file, checks its hash, replays it and challenges
   (posting its own bond) if the result differs (`WRONG_RESULT`) or the evidence is bad (`EVIDENCE_INVALID`).
6. **Resolve.** A designated resolver settles a challenge within the **300 s resolution window**: the winner is
   credited 2× bond. If the resolver does not act, `expireUnresolved` refunds both sides. Payouts are pull-based
   (`withdraw`).
7. **Act.** An unchallenged claim finalizes after the window. `DemoVault.applyClaim` reads it: residual bad debt
   ≥ $1,000 lowers max LTV from 80% to **50%**; above $4,000 pauses borrowing (local deploy thresholds). `MockLendingMarket` enforces it
   (`LtvTooHigh` revert).

The verdict is always the deterministic replay. The LLM, the graph and the UI never decide a dispute.

## Architecture and technology

```
 pipeline/ (Python)  ──snapshot──►  core/ stressproof_core (pure Python, integer math)
                                         │ replay + canonical case file
                                         ▼
 backend/ FastAPI ── /stress/run, /case-files, /replay-reports, /replay-outputs, /feed
   storage: filesystem or Postgres (content-addressed raw bytes)
        ▲                     ▲                       ▲
        │ agents/ (Python, web3.py): attester · watcher · resolver CLI · malicious attester (demo)
        │                     │ postClaim / challenge / resolve / finalize
        │                     ▼
        │      contracts/ (Solidity, Foundry): StressRegistry ─finalized claim─► DemoVault ─► MockLendingMarket
        │                     ▲
 frontend/ Next.js 14 App Router · wagmi 2 / viem · RainbowKit · Tailwind  (reads chain + backend, signs with wallet)
```

Full explanation for evaluators, including trust boundaries: [docs/architecture.md](docs/architecture.md).

| Area | What is in the repository |
|---|---|
| `contracts/` | `StressRegistry` (bonds, windows, dispute state machine, pull payments), `DemoVault` (circuit breaker), `MockLendingMarket`; Foundry unit, resolution and invariant tests |
| `core/` | Canonical JSON, keccak hashing, case-file validation (V-01…V-14), replay, verdict |
| `backend/` | FastAPI service: stress runs, content-addressed case files and replay reports, read-only replay outputs, durable feed; filesystem or Postgres storage |
| `agents/` | Attester, watcher (fetch → hash check → replay → challenge), resolver CLI, scripted malicious attester |
| `frontend/` | Landing, dashboard, stress simulation, claims (publish, challenge, finalize, expire, withdraw), vault (apply, borrow check), feed, exposure graph |
| `pipeline/` | Aave v3 snapshot extraction, synthetic accounts, normalization, threshold sweep |

## Key components

- **Deterministic replay and evidence verification.** The replayer is pure and integer-only. Case files are
  served as exact bytes; the frontend, watcher and resolver each recompute keccak-256 over the raw bytes and
  refuse anything that does not match the on-chain `evidenceHash`.
- **Bonded claims and disputes.** Fixed 0.01 ETH bond; 120 s challenge and 300 s resolution windows; outcomes
  Finalized, Rejected or Expired; winnings credited and withdrawn by the recipient.
- **Watcher and resolver.** The watcher polls the registry, verifies and replays each pending claim and
  challenges mismatches. The resolver CLI replays the disputed claim and submits the deterministic verdict. The
  resolver key is trusted in this MVP (disclosed below).
- **Vault circuit breaker.** `DemoVault` applies a finalized claim once: 80% → 50% max LTV at $1,000 residual
  bad debt, borrow pause above $4,000 (local deploy thresholds). `MockLendingMarket` reverts borrows above the active limit.
- **AI scenario proposal.** The attester's scenario input is a separate, untrusted stage: a proposer chooses the
  shock and rationale, and the deterministic replay checks everything after it. **Current implementation:** the
  attester uses a fixed scenario (`FIXED_SCENARIO_SHOCK_BPS`, default −3000 bps). The LLM proposer (WP-7) is
  designed in `docs/phase2_execution_plan.md` but **not implemented** (no API key, SDK not added).
- **Exposure graph (`/graph`, WP-6).** Draws one replay as accounts, assets, market, case file and on-chain
  claims, built only from the hash-verified case file, `GET /replay-outputs/{hash}` and claims that commit to
  that hash. It shows the source of every value, recomputes the case-file totals from the per-account rows,
  and is informational only. A separate panel shows the live TigerGraph exposure query through
  `GET /graph/exposure`, labelled REAL TIGERGRAPH RESULTS, SYNTHETIC FIXTURE DATA or TIGERGRAPH UNAVAILABLE.
  TigerGraph never affects a verdict.
- **Wallet safety (WP-13).** Writes go only to the configured chain; a wrong network is refused before
  anything is signed. Challenge, finalize and expire are simulated before signing. Reverted receipts show the
  decoded reason.

## Status: implemented, verified, mocked, pending

| Item | Status |
|---|---|
| Contracts, replay, backend, agents, frontend | **Implemented** and covered by tests |
| Full flow on local Anvil (publish, challenge, resolve, finalize, expire, apply, borrow check, withdraw) | **Verified locally**: GATE-24 local 101/101; wallet flows exercised in the browser with an injected test wallet |
| Same flows with the MetaMask extension | Manual check by the project owner (see the demo guide) |
| Dataset | **SYNTHETIC** fixture (6 accounts). The real-data pipeline exists but no real snapshot ships |
| Lending market | **Mocked** (`MockLendingMarket`); short windows and thresholds chosen so effects are visible |
| Base Sepolia deployment and testnet acceptance (GATE-24 steps 3–7) | **Pending**: needs funding and deploy authorization |
| TigerGraph integration (WP-2..5): schema, loader, reconciler, exposure query, `/graph/exposure`, UI panel | **Implemented and tested against a fake TigerGraph; live Savanna connection not yet verified** (needs workspace credentials, see `tigergraph/README.md`) |
| LLM scenario proposer (WP-7) | **Not implemented** |
| Next.js 15.5.28+ migration | **Pending** (open security task, see Supply-chain scan) |

## Local setup

Prerequisites: Foundry, `uv` (Python 3.11+), Node.js 20+ with npm.

```bash
uv sync                                   # Python workspace
(cd frontend && npm install)              # frontend
cp .env.example .env                      # local values only; never commit .env
cp frontend/.env.example frontend/.env    # set NEXT_PUBLIC_CHAIN_ID=31337
```

Run the stack (one terminal each):

```bash
make chain          # Anvil on 127.0.0.1:8546, chain 31337
make deploy-local   # deploys contracts, writes deployments/31337.json
make backend        # FastAPI on :8000
make web            # Next.js on :3000 (uses pnpm; or: cd frontend && npm run dev)
make watcher        # optional: the watcher agent
```

The step-by-step demo, including MetaMask on Anvil: [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md).

## Test results (2026-10-30, local)

| Suite | Command | Result |
|---|---|---|
| Contracts | `cd contracts && forge test` | **95 passed**, 0 failed (6 suites, including invariants) |
| Python (core, backend, agents, pipeline, scripts) | `uv run pytest` | **739 passed**, 64 skipped (Postgres tests need `TEST_DATABASE_URL`) |
| Frontend | `cd frontend && npx vitest run` | **217 passed** (23 files) |
| Types | `cd frontend && npx tsc --noEmit --incremental false` | clean |
| Local end-to-end gate | GATE-24 local checks | **101/101 passed** (earlier run) |
| Testnet acceptance | GATE-24 steps 3–7 on Base Sepolia | **not run** |

## Limitations

- Base Sepolia is not deployed; nothing has run on a public chain.
- The dataset is SYNTHETIC; results say nothing about real Aave.
- One-pass, full-liquidation model with no slippage (see Disclosure Statement).
- A single designated resolver is trusted; at least one watcher must be live.
- Next.js 14.2.35 still carries advisories; the Image Optimization RCEs are mitigated by configuration, the
  rest need the tracked migration.
- The graph shows one replay at a time and at most 400 accounts per filter.

## Repository map

* `contracts/` Foundry project: contracts, deploy scripts, unit and invariant tests.
* `core/` deterministic replay library (`stressproof_core`).
* `pipeline/` Aave v3 snapshot pipeline.
* `backend/` FastAPI service ([endpoints](backend/README.md)).
* `agents/` attester, watcher, resolver CLI, malicious attester.
* `frontend/` Next.js app.
* `deployments/` addresses and constants per chain id (`84532.json` is not a live deployment yet).
* `data/fixtures/` golden SYNTHETIC fixtures shared across languages.
* `docs/` architecture, plans, schemas, security, submission and demo guides.
* `scripts/` deploy, ABI export, E2E, preflight and Socket scan scripts.

StressProof is a single-owner project (see `CONTRIBUTING.md`, Governance).

---

## Supply-chain scan (Socket)

**Status (2026-10-30): Socket scans run by the project owner (organization `madhavan`).**

| Scan | Report level | Result |
|---|---|---|
| `b8de24a7-8330-468d-bc77-7ac8715c5d27` | `error` | `healthy: true`, no alerts |
| `a614ab24-c711-4213-995f-ef3897aef829` | `warn` | `healthy: true`, 3 `criticalCVE` alerts (policy `warn`), all npm; none for Python |
| `bcb264df-5ee2-439e-889d-35c7ad023df9` (latest, after the vitest upgrade) | `warn` | `healthy: true`, **1 alert: `next` 14.2.35 `criticalCVE`** (policy `warn`); vitest and tinypool alerts gone |

No malware, typosquat, install-script or other supply-chain alerts were reported in any scan. The
warn-level alerts and what was done:

| Package (version) | Socket alert | Action |
|---|---|---|
| `vitest` 1.6.1 (dev, direct) | criticalCVE (GHSA-5xrq-8626-4rwp, fixed in 3.2.6) | **Fixed:** upgraded to `vitest` 4.1.12 (pinned; released 2026-08-18). All 164 frontend tests pass unchanged |
| `tinypool` 0.8.4 (dev, via vitest) | criticalCVE (GHSA-5gmw-xhrv-c9v3, GHSA-85c8-ppgw-ccpr, fixed in 2.1.2) | **Fixed:** vitest 4 no longer depends on tinypool; it is gone from the lockfile |
| `next` 14.2.35 (runtime, direct) | criticalCVE (GHSA-2xp9-vwfh-vxw4, GHSA-2464-fhr4-w9xw, GHSA-p293-qw3h-jr36, fixed in 15.5.28) | **Mitigated, not fixed:** no patched 14.2.x exists. The two Image Optimization RCEs are unreachable because the optimizer is disabled (`images.unoptimized: true`); the third affects Windows-hosted servers only. Fixing it needs the Next.js 15.5.28+ migration (tracked) |

**Provenance of the latest scan:** it uploaded the lockfiles on disk after the vitest upgrade, which is
not committed yet, so the Socket dashboard labels it with the previous commit (`0d354a2`). Re-scan after
committing (or let the CI workflow run on push) for a scan that matches a commit exactly. The script now
warns when it scans uncommitted manifest changes.

**Next.js mitigation, verified:** with `images.unoptimized: true`, Next.js 14.2.35 answers `/_next/image`
with a 404 before parsing parameters or reading any image (checked in its server code and against the
running dev server). It protects a deployment only once this configuration is committed and deployed.
**Open security task:** migrate to Next.js 15.5.28 or later to remove the `next` criticalCVE and the
App Router Server Component denial-of-service and cache-poisoning advisories.

**What Socket scans:** `frontend/package.json` + `frontend/package-lock.json` (npm) and the uv workspace
(`pyproject.toml` files + `uv.lock`, PyPI). Foundry's `forge-std` is a git submodule, which Socket does
not cover; it is excluded in `socket.yml`.

**How to run it:**

1. Create a Socket API token with the scopes `full-scans:create`, `full-scans:list` and
   `security-policy:read`.
2. Locally: `export SOCKET_CLI_API_TOKEN=…` (never commit it), then `make socket-scan`. The report is
   written to `socket-report/socket-scan.json` (git-ignored). The CLI is pinned to `socket@1.8.3`.
3. In CI: add the token as the repository secret `SOCKET_SECURITY_API_TOKEN`; the workflow
   `.github/workflows/socket-scan.yml` runs the same script on pushes and pull requests and fails with
   "Socket scan NOT RUN" when the secret is missing.
4. Alternatively, install the Socket GitHub App on the repository; it reads `socket.yml`.

**Other dependency checks (not Socket), run 2026-10-30 on commit `0d354a2` plus local changes, after the vitest upgrade:**

| Check | Result |
|---|---|
| `uv audit` (Python, 69 packages) | No known vulnerabilities |
| `uv lock --check` | `uv.lock` consistent with the workspace |
| `npm ls --package-lock-only` | `package-lock.json` consistent with `package.json` |
| `npm audit --package-lock-only` (662 packages) | 32 advisories: 1 critical (`next`), 17 high, 12 moderate, 2 low; none in dev-only tooling. Before the vitest upgrade: 37 (3 critical) across 714 packages. None of the rest has a non-breaking fix |
| Install scripts (S-13) | 5 packages declare them: `bufferutil`, `keccak`, `utf-8-validate`, and dev-only `esbuild`, `fsevents`. npm 11 holds back unapproved install scripts; the frontend tests and the dev server run without them (these packages have JavaScript fallbacks) |

**Triage of the npm advisories:**

- **Next.js 14.2.35 (25 advisories, 3 critical).** Not reachable here: Server Actions, middleware,
  rewrites, custom servers, i18n Pages Router, CSP nonces and Windows hosting are all unused. The Image
  Optimization API (two critical RCE advisories with crafted AVIF/SVG, plus DoS and disk-growth issues)
  existed by default even though no `next/image` is used; it is now **disabled** with
  `images.unoptimized: true` (tested). **Still applicable:** App Router Server Component denial-of-service
  and cache-poisoning advisories. Next.js 15.5.28 fixes the three critical advisories; `npm audit`
  suggests 16.4.3 to clear every Next.js advisory. Either is a major migration, not done here.
- **Dev and test tooling (vitest, vite, vite-node, esbuild, tinypool; 2 critical).** **Fixed** by the
  upgrade to vitest 4.1.12 (Vite 8.3.5, no tinypool): no dev-only advisories remain. Vite 8.3.5 was nine
  days old at install; Socket and npm audit report nothing for it.
- **Wallet stack (wagmi 2, viem, WalletConnect/Reown, MetaMask SDK, and transitive `ws`, `zod`, `uuid`,
  `query-string`, `abitype`, `decode-uri-component`; up to high).** Mostly denial-of-service and memory
  issues in client-side libraries. Fixed only by wagmi 3 / RainbowKit changes, which need a tested
  migration of the wallet flows.

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
