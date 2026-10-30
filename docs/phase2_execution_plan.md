# StressProof — Phase 2 Execution Plan (active, conditional)

| | |
|---|---|
| `GATE-24` | **PENDING TESTNET ACCEPTANCE** |
| `PHASE 2` | **CONDITIONAL START APPROVED** (sole project owner, 2026-10-30; `phase2_gate_amendment.md` §9) |
| `FINAL RELEASE` | **BLOCKED UNTIL GATE-24 PASSES** |
| Prepared | 2026-10-30, from commit `0d354a2` |
| Basis | `docs/phase2_gate_amendment.md` §4 (16-item matrix), `docs/implementationplan.md` §17, §18, §20, §21, §24–26 |

ALLOWED and CONDITIONAL packages may start now. BLOCKED packages wait for the GATE-24 evidence in
`phase2_gate_amendment.md` §7. GATE-24 stays a parallel milestone with priority (§5).

---

## 1. Approval record

The sole project owner approved the conditional Phase 2 start on 2026-10-30 (`phase2_gate_amendment.md`
§9). The earlier request for separate approvals from Developers 1, 2 and 3 is superseded by single-owner
governance (`CONTRIBUTING.md`, Governance); no individual developer approvals were collected.

---

## 2. Ownership

StressProof is a single-owner project: the project owner is responsible for every work package and may
change any part of the repository. The "original area lead" noted in each package records who first built
that subsystem, for context only:

| Area | Original area lead |
|---|---|
| `frontend/` | Developer 1 |
| `core/`, `pipeline/`, `backend/` | Developer 2 |
| `contracts/`, `agents/`, Phase 2 TigerGraph and LLM | Developer 3 |

The earlier open question about the TigerGraph loader and reconciler files under `pipeline/` is closed:
the project owner decides where they live.

---

## 3. Work packages

Rules for every package: never import TigerGraph or LLM code into `stressproof_core` replay or
validation, the watcher's verdict logic or the resolver; no change to `IStressRegistry.sol`, ABIs,
schemas or `deployments/*.json` outside the `ABI:` / `SCHEMA:` process; local Anvil or mocks only; no
testnet transactions; secrets only in git-ignored env files; synthetic data labelled SYNTHETIC.

Before merging anything that touches `agents/`, `core/`, `contracts/` or `backend/`: `forge test`,
`pytest`, frontend tests, `tsc`, and a local `e2e_local.sh` re-run.

### WP-1 Socket scan — **ALLOWED**
- **Deliverables:** Socket report for `uv.lock` and the frontend lockfile; flagged packages fixed or
  pinned with reasons; README section "Supply-chain scan" (plan S-13, "never cut").
- **Original area lead:** Developer 3. **Collaborators:** Developer 1 (frontend lockfile), Developer 2 (Python deps).
- **Dependencies:** Socket access (plan marks its CLI usage **[UNVERIFIED]**; follow Socket's docs).
- **Files:** `README.md`; possibly `uv.lock`, `pyproject.toml`, `frontend/package.json`, the frontend lockfile.
- **Acceptance:** the report is in the README; every flagged package is resolved or justified; all suites green after any lockfile change.
- **Tests:** full suites and a local E2E re-run if any dependency changes.
- **Security:** no new post-install scripts; no tokens committed.

**WP-1 status (2026-10-30): COMPLETE (Socket scans run and every flagged package fixed or justified).**

- **Implemented:** `socket.yml` (version 2; excludes the `contracts/lib` submodule), `scripts/socket_scan.sh`
  (pinned `socket@1.8.3`, `scan create --report --json`, token from the environment only), `make socket-scan`,
  `.github/workflows/socket-scan.yml` (secret `SOCKET_SECURITY_API_TOKEN`; fails as "NOT RUN" without it),
  README section "Supply-chain scan (Socket)", `docs/security.md` S-13 corrected (npm lockfile, not pnpm).
- **Socket coverage:** npm (`frontend/package.json`, `package-lock.json`) and PyPI (`pyproject.toml` files, `uv.lock`).
  Not covered: Foundry `forge-std` (git submodule).
- **Socket results (org `madhavan`, run by the project owner):** scan `b8de24a7-…` at level `error`: healthy, no alerts.
  Scan `a614ab24-c711-4213-995f-ef3897aef829` at level `warn`: healthy, 3 npm `criticalCVE` alerts (policy `warn`), none for
  Python, no malware/typosquat/install-script alerts.
  - `vitest` 1.6.1: **fixed** (upgraded to 4.1.12, pinned). `tinypool` 0.8.4: **fixed** (removed; vitest 4 does not use it).
  - `next` 14.2.35: **mitigated, not fixed** (Image Optimization API disabled; Windows-only RCE not applicable). Fix needs
    Next.js 15.5.28+; tracked below.
  - Scan `bcb264df-5ee2-439e-889d-35c7ad023df9` (latest, `warn`, after the vitest upgrade): healthy, **only `next` 14.2.35
    `criticalCVE` remains**; vitest and tinypool alerts gone. It used the uncommitted lockfiles on disk, so it is labelled
    with commit `0d354a2`; re-scan after committing for exact commit provenance.
  - Whether the CLI exits non-zero on policy errors is unconfirmed (no run has had one).
- **Non-Socket checks:** `uv audit` clean (69 packages); `uv lock --check` and `npm ls --package-lock-only` consistent;
  `npm audit` 37 advisories (3 critical, 18 high, 14 moderate, 2 low), none fixable without a major upgrade.
- **Remediation performed:** Next.js Image Optimization API disabled (`images.unoptimized: true`; the app uses no
  `next/image`). `vitest` upgraded 1.6.1 → 4.1.12 (dev only), removing tinypool, vite-node and the old vite/esbuild:
  npm audit went from 37 advisories (3 critical) to 32 (1 critical, `next`), with none left in dev tooling.
- **Outstanding security tasks:**
  1. **Next.js 15.5.28+ migration (open, highest priority):** removes the remaining `next` criticalCVE and the App Router
     Server Component DoS / cache-poisoning advisories. Until then the Image Optimization API stays disabled (verified:
     `/_next/image` returns 404 before any processing); the mitigation reaches a deployment only once committed and deployed.
  2. wagmi 3 / RainbowKit wallet-stack migration (client-side DoS and memory advisories), with the WP-13 wallet flows re-tested.
  3. Re-scan after committing the vitest upgrade so the Socket report matches a commit exactly.
- **Tests:** 7 script tests (`scripts/tests/test_socket_scan_sh.py`, stubbed CLI, token never on a command line or in
  output) and 2 config tests (`frontend/tests/nextConfig.test.ts`).

### WP-2 TigerGraph workspace and schema — **CONDITIONAL**
- **Deliverables:** workspace created; `tigergraph/schema.gsql` per plan §17.1 (corrected schema C-05).
- **Original area lead:** Developer 3. **Collaborators:** Developer 2 (snapshot fields).
- **Dependencies:** a TigerGraph account and credentials (none yet); dataset decision (only the 6-account synthetic fixture exists).
- **Files:** `tigergraph/schema.gsql` (new), `.env.example` (variable names only).
- **Acceptance:** the schema applies cleanly; no credentials in git.
- **Tests:** a schema lint or dry-run if available; a unit test that the schema file parses.
- **Security:** TG credentials only in git-ignored env files.

### WP-3 Loader and reconciler — **CONDITIONAL**
- **Deliverables:** `tg_load.py` (pipeline step 5) and `tg_reconcile.py` (step 6), which **must fail loudly on mismatch** (§17.2–17.3).
- **Original area lead:** Developer 3 (feature); the files sit in `pipeline/` (originally Developer 2).
- **Dependencies:** WP-2; `data/datasets/*/snapshot.json`; `data/replay_outputs/*.jsonl`.
- **Files:** `pipeline/src/stressproof_pipeline/` (new modules), `pipeline/tests/`.
- **Acceptance:** loading the fixture then reconciling succeeds; any count or sum mismatch exits non-zero with a clear message.
- **Tests:** mocked TigerGraph client: matching data passes; each mismatch type fails loudly.
- **Security:** read-only from the verdict path's perspective; data-class labels preserved (S-16).

### WP-4 Graph queries (Appendix C) — **CONDITIONAL**
- **Deliverables:** `top_debt`, `near_liquidation` and the other Appendix C queries.
- **Original area lead:** Developer 3. **Dependencies:** WP-2, WP-3; GSQL syntax **[UNVERIFIED]** (check in GraphStudio).
- **Files:** `tigergraph/queries/` (new), a Python wrapper under the owning package.
- **Acceptance:** each query returns expected results on the fixture.
- **Tests:** wrapper unit tests with recorded fixture responses.
- **Security:** results never feed a verdict.

### WP-5 `/graph/exposure` route and UI integration — **CONDITIONAL**
- **Deliverables:** replace the 503 stub with real data; colours; real/synthetic filter.
- **Original area lead:** Developer 2 (route). **Collaborators:** Developer 1 (UI), Developer 3 (data source).
- **Dependencies:** WP-3 for live data (may serve `replay_outputs` first).
- **Files:** `backend/src/stressproof_backend/api/routes/graph.py`, `backend/tests/`, `frontend/src/app/graph/page.tsx`.
- **Acceptance:** the route returns labelled nodes and edges; the UI renders them with the data-class banner; it returns 503 with a clear message when the graph is unavailable.
- **Tests:** backend route tests (available and unavailable); frontend unit test for the label.
- **Security:** no addresses beyond what the snapshot already exposes; labels kept.

**WP-2 to WP-5 status (2026-10-30, frozen for submission): schema created in Savanna by the project owner (5 vertex types, 6 edge types); CSV data loading PENDING; no live TigerGraph data connected.**
Schema `tigergraph/schema.gsql`, read-only query `tigergraph/queries/sp_exposure.gsql`, SYNTHETIC CSVs in
`tigergraph/data/` (11 vertices, 27 edges, generated from the golden fixture with the core replayer), REST client,
idempotent loader and fail-loud reconciler, and setup CLI in `backend/src/stressproof_backend/tigergraph/`.
`GET /graph/exposure` runs the installed query, reconciles its totals with the stored case file, and answers
503 when TigerGraph is not configured or unreachable. The `/graph` page shows REAL TIGERGRAPH RESULTS /
SYNTHETIC FIXTURE DATA / TIGERGRAPH UNAVAILABLE. Tested against a fake TigerGraph (httpx mock transport). The
live run needs Savanna workspace credentials (see `tigergraph/README.md`). The files sit in the backend
package rather than `pipeline/`, because the backend already has `httpx`.

### WP-6 Graph page skeleton from `replay_outputs` — **ALLOWED**
- **Deliverables:** static graph built from `data/replay_outputs/<evidenceHash>.jsonl` (plan §24 H24–26).
- **Original area lead:** Developer 1. **Collaborators:** Developer 2 (data format, §8.5).
- **Dependencies:** existing replay outputs.
- **Files:** `frontend/src/app/graph/page.tsx`, a new loader in `frontend/src/lib/`.
- **Acceptance:** the page renders the accounts and outcomes for a chosen evidence hash with the SYNTHETIC banner.
- **Tests:** vitest for the parser (valid, empty and malformed input).
- **Security:** render values as text.

**WP-6 status (2026-10-30): COMPLETE (local; informational only, no verdict, contract or ABI change).**

- **Backend (additive, read-only):** `GET /replay-outputs/{evidenceHash}` returns the stored JSONL (same
  hash check as case files; 404 when absent; no keccak header because the bytes are derived). `get_replay_outputs`
  added to the filesystem and Postgres stores. `/graph/exposure` (503 stub) is unchanged and not used.
- **Frontend:** `/graph` page. Loader `frontend/src/lib/graph/` fetches the case file, checks that its bytes
  hash to the evidenceHash (otherwise nothing is drawn), then parses the outputs strictly (exact keys, integer
  strings, safe ids; one bad line or a duplicate id fails the file). Nodes: case file, market, collateral asset,
  stablecoin debt, accounts (coloured by outcome) and on-chain claims that commit to the evidenceHash. Edges:
  account→collateral, account→debt, market→assets, case file→market, claim→case file. No account-to-account
  edges, because the data has none. Custom SVG with a fixed column layout, wheel/button zoom, drag pan,
  keyboard selection, outcome filter, id search, legend, info panel with a source tag on every value
  (REPLAY OUTPUT / CASE FILE / ON CHAIN), a consistency panel that recomputes the four case-file totals from
  the per-account rows, an account table, the SYNTHETIC banner, and idle, loading, invalid-hash,
  case-file-missing, outputs-unavailable, malformed and backend-unreachable states. No new dependency.
- **Evidence picker:** hashes from on-chain claims (newest 50), then from backend `CLAIM_BUILT` feed entries,
  plus manual paste and `?evidence=<hash>`.
- **Tests:** backend `test_api.py` (served bytes, 400, 404, read-only); vitest `graph.test.ts` and
  `graphLoader.test.ts` (parser valid/empty/malformed/duplicates, case-file shape, node and edge generation,
  SYNTHETIC labels, consistency checks, filter, search, render cap, layout, selection, loader states, zoom/pan,
  evidence options). Fixture outputs generated by `stressproof_core.replay` from the golden case file.
- **Browser check:** local backend and dev server, desktop and 375 px: graph, selection, filter, search,
  zoom, pan, keyboard, paste, invalid and missing states.
- **Limits:** shows one replay at a time; at most 400 accounts drawn per filter; no pinch zoom on touch
  (buttons and drag work); the outputs-unavailable state was checked in unit tests only.

### WP-7 LLM scenario proposer — **CONDITIONAL**
- **Deliverables:** `agents/.../llm_scenario` per plan §18.2: compact numeric context with no addresses; JSON-only reply; strict validation (`shockBps` integer in [−9000, −1], rationale trimmed to 4,000 characters, control characters stripped); retry once, then fall back to `FIXED_SCENARIO_SHOCK_BPS`; `promptHash` and model id in the feed entry.
- **Original area lead:** Developer 3. **Collaborators:** Developer 2 (`/stress/run` contract).
- **Dependencies:** an LLM API key (none yet); the SDK is not in `uv.lock` (team decision before adding); WP-4 for graph context (a fixed context may be used first).
- **Files:** `agents/src/stressproof_agents/attester/` (new module), `agents/tests/`, `.env.example` (names only).
- **Acceptance:** valid, invalid and missing outputs all yield a validated scenario or the fallback; the rationale is committed through `evidenceHash`; the AI never decides a verdict, signs or holds keys (§18.1).
- **Tests:** T-P-60 malformed-output cases with a mocked model; a test that the watcher and resolver import nothing from the LLM module.
- **Security:** prompt-injection posture per §18.2 item 5; no keys in prompts or logs.

### WP-8 LLM claim end to end on the testnet — **BLOCKED**
- **Deliverables:** an LLM-proposed claim posted, verified and finalized on Base Sepolia (Phase 2 done criterion).
- **Original area lead:** Developer 3. **Dependencies:** GATE-24 evidence (amendment §7). Local Anvil end to end is allowed under WP-7.

### WP-9 Rationale and feed display — **CONDITIONAL**
- **Deliverables:** the rationale in the claim detail as plain text; a feed line "LLM proposed −X bps".
- **Original area lead:** Developer 1. **Dependencies:** WP-7's output shape (fixtures until then); schema changes need a `SCHEMA:` commit.
- **Files:** `frontend/src/app/claims/[id]/page.tsx`, `frontend/src/app/feed/page.tsx`, `frontend/src/lib/`.
- **Acceptance:** the rationale renders as text; script tags show literally.
- **Tests:** an XSS test (T-F-05) and a formatting test.
- **Security:** never render HTML or markdown (S-11).

### WP-10 Agent feed polish — **ALLOWED**
- **Deliverables:** clearer feed entries, filtering and empty states (plan §25).
- **Original area lead:** Developer 2 (backend). **Collaborators:** Developer 1 (UI).
- **Dependencies:** the existing feed schema (C-04).
- **Files:** `backend/src/stressproof_backend/api/routes/feed.py`, `frontend/src/app/feed/page.tsx`.
- **Acceptance:** no schema break; entries stay labelled "agent-reported" (S-10).
- **Tests:** backend feed tests; frontend feed parsing tests.
- **Security:** bearer token on writes unchanged.

### WP-11 Assumptions text, banners, empty and error states — **ALLOWED**
- **Deliverables:** final assumptions panel (§10.4 word for word), banners, empty and error states (§24 H29–32).
- **Original area lead:** Developer 1.
- **Files:** `frontend/src/app/stress/`, `frontend/src/components/`.
- **Acceptance:** the text matches §10.4; no wording implies testnet acceptance or GATE-24.
- **Tests:** vitest snapshots of the assumptions text.
- **Security:** none beyond text rendering.

### WP-12 Security pass and local E2E re-run — **ALLOWED (local)**
- **Deliverables:** a review against plan §20 (S-01 to S-19) with findings recorded; `e2e_local.sh` re-run at the current commit.
- **Original area lead:** Developer 3. **Collaborators:** Developer 2.
- **Files:** a findings note under `docs/`; fixes only through normal review.
- **Acceptance:** each S-item checked with a test reference; the local E2E passes.
- **Tests:** existing suites plus local E2E (Anvil only).
- **Security:** no testnet writes; contract changes would invalidate the gate evidence and need a team sync.

### WP-13 Wallet-signed transaction UX on local Anvil — **ALLOWED (local)**
- **Deliverables:** with MetaMask on Anvil 31337, complete in the browser: publish claim (0.01 ETH bond), challenge, finalize, expire, withdraw, apply to vault, try borrow with the decoded revert (plan §24 C5/C6, acceptance criteria 1, 3, 6, 7).
- **Original area lead:** Developer 3. **Collaborators:** Developer 1.
- **Dependencies:** the local stack (Anvil, local deploy, backend); a browser wallet on 31337.
- **Files:** `frontend/src/app/stress/page.tsx`, `frontend/src/app/claims/`, `frontend/src/app/vault/page.tsx`, `frontend/src/lib/web3/` (fixes only if a flow fails).
- **Acceptance:** each flow completes with a confirmed receipt and the UI refreshes; wrong-chain and missing-wallet states block writes; a written run log with local transaction hashes.
- **Tests:** existing write-guard tests; new unit tests for any bug fixed; the manual checklist T-F-10.
- **Security:** keep the chain, bond, bytecode and receipt checks; never auto-send after connecting.

### WP-14 Demo dry run and testnet rehearsal — **BLOCKED**
- **Deliverables:** timed demo script and full rehearsal on the testnet, backup video (plan §24 H32–34, Phase 3).
- **Original area lead:** everyone. **Dependencies:** testnet deployment and GATE-24.

### WP-15 Flow voice input, Dodo Payments narrative — **CONDITIONAL**
- **Deliverables:** only if the sponsor's bounty text requires it and it fits in under an hour (plan §24 Phase 3, §26: cut first).
- **Original area lead:** Developer 1 unless reassigned. **Dependencies:** the bounty text read first (APIs **[UNVERIFIED]**).
- **Security:** isolated from the verdict path.

### WP-16 Cake Wallet — **CONDITIONAL (read-only) / BLOCKED (writes)**
- **Status:** connection and browse-only display work; Cake Wallet cannot sign on 31337 or 84532.
- **Original area lead:** Developer 1, Developer 3. **Writes require** a deployment on a chain Cake Wallet supports, which is out of scope.

---

## 4. First task: WP-13, wallet-signed flows on local Anvil (complete locally; MetaMask manual check by the owner)

Why WP-13 comes first:

1. **It lowers GATE-24 risk directly.** Acceptance criteria 1, 3, 6 and 7 must be shown **in the UI**
   during the H24 testnet run, and no wallet-signed browser flow has been completed yet, even on Anvil.
   Finding UI bugs now avoids burning test ETH and the team's joint session on them later.
2. **It needs nothing that is missing.** Local Anvil and MetaMask only: no testnet contracts, no
   TigerGraph or LLM credentials, no new dependencies.
3. **It is owned and bounded.** Developer 3 with Developer 1, per the plan's Phase 2 table
   ("Help C with the transaction UX"), with clear pass criteria (receipts and UI state per flow).
4. **It does not touch the verdict path or contract interfaces.** Fixes, if any, stay in the frontend.

Run in parallel if time allows: **WP-1 (Socket scan)**, which has zero chain dependency and is a "never cut" item.

### WP-13 status (2026-10-30)

Exercised in the browser on local Anvil (chain 31337) through the app's real wallet code, using an
injected EIP-1193 test wallet backed by Anvil's public dev accounts (not MetaMask): connect,
account shown in the header, account change, wrong network (writes refused, nothing sent),
rejection, disconnect, publish (receipt checked on chain), challenge, finalize, expire, apply,
borrow check (70% passes at 80% LTV, reverts `LtvTooHigh(7000, 5000)` at 50%), withdraw (payout
checked on chain).

Defects found and fixed:

1. **Reverted transactions showed as pending forever.** wagmi's `useWaitForTransactionReceipt` throws
   on a reverted receipt; all four write pages now use `useTxReceipt` (viem receipt, reverted
   included, with the decoded reason).
2. **No way to collect pull payments.** Added the credits panel with Withdraw on the claims page.
3. **Challenge form defaults could never succeed:** a placeholder report URI that the backend cannot
   serve, and a counter equal to the claim (`CounterEqualsClaim`). Both now start empty with hints.
4. **Challenge, finalize and expire were signed without a simulation**, so predictable reverts were
   mined. They are now simulated first and explained.
5. **No Expire button** for challenged claims past the resolution window (the handler existed but was
   never rendered).
6. **A stale borrow result** stayed on screen after the vault limit changed.
7. **The wrong-network message blamed Cake Wallet** for any wallet on a Cake-supported chain.

Still to verify by the project owner: the same flows with the real MetaMask extension on Anvil.
Local-only note: Anvil mines blocks only when transactions arrive, so the UI's chain clock and
pre-sign simulations can lag real time; on Base Sepolia blocks arrive about every 2 s.

---

## 5. GATE-24 parallel checklist (remains the first priority)

| # | Step | Status | Owner | Notes |
|---|---|---|---|---|
| G1 | Remaining Base Sepolia funding: attester, watcher and malicious attester each need 0.009 ETH more (0.027 ETH in total) | **Open** | Project owner | Deployer and resolver already meet their minimums |
| G2 | `make testnet-preflight` passes | Passing | Project owner | Re-run just before deploying |
| G3 | Explicit authorization, then `ENV_FILE=.env.testnet make deploy-testnet` | **Open** | Project owner | Writes `deployments/84532.json` from receipts; commit it |
| G4 | Read-only checks of deployed bytecode, parameters and role addresses | Open | Project owner | |
| G5 | Honest claim: post; watcher `HASH_OK` / `REPLAY_MATCH`; no challenge | Open | Project owner | Step 3 |
| G6 | Real 120 s wait; `finalize`; `applyClaim`; `maxLtvBps == 5000`; 70% borrow reverts `LtvTooHigh` in the UI | Open | Project owner | Step 4 |
| G7 | Malicious 3R claim; watcher `WRONG_RESULT` with counter = R inside the window | Open | Project owner | Step 5 |
| G8 | Resolver upholds within 300 s; claim Rejected; watcher withdraw delta `+BOND` | Open | Project owner | Step 6 |
| G9 | `applyClaim(maliciousId)` reverts `NotFinalized` in the UI | Open | Project owner | Step 7 |
| G10 | In-browser hash verification green for both case files | Open | Project owner | Criterion 7 |
| G11 | The project owner observes the full testnet run; name and date recorded (amendment §8, owner decision 2026-10-30) | Open | Project owner | |
| G12 | Record transaction hashes, block numbers, watcher log lines and balance deltas | Open | Project owner | Evidence for amendment §8 |

No step above is performed by this document. Funding, deployment and transactions each need the team's explicit action.
