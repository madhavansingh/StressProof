# StressProof (working title)

**An open, challengeable layer for AI-generated lending-market risk claims.**

> AI agents propose lending-market stress-test claims with real money at stake. Other agents verify them by independent replay and earn the bond when they catch a wrong result. Finalized claims can trigger on-chain controls on a mock lending market.

| | |
|---|---|
| **Hackathon** | Hacker House Goa |
| **Main track** | AI x Crypto |
| **Partners on the event page** | Flow (voice AI), Cake Wallet, AI Grants India Foundation, Dodo Payments, Edge City India, Socket, TigerGraph |
| **Team** | Person A (contracts), Person B (backend, agents, replay), Person C (frontend) |
| **Build window** | About 40 hours |
| **Revision** | v2: replay scope, metric definitions, case-file retrieval, claim state machine, data pipeline |

> **Confirm before building:** the event page lists seven partners but does not say which run prize tracks or what qualifies. Read each partner's bounty text and update Section 3 where it differs.

---

## 0. MVP Goal and Build Order

**Get this flow working end to end before anything else:**

1. Generate a claim (snapshot, scenario, replay, case file, post on-chain with bond)
2. Independently replay it (watcher fetches the case file, verifies its hash, recomputes)
3. Challenge an incorrect claim
4. Resolve the dispute (designated resolver)
5. Transfer the bonds correctly
6. Show a finalized claim changing the mock-vault controls

Everything else (LLM scenario selection, TigerGraph-driven scenarios, voice, payments, wallet integrations, graph animation) is layered on after this flow passes. Phase 1 uses a fixed scenario config.

## 1. Problem

Protocols and DAOs act on risk analysis from closed providers and, increasingly, from AI agents. Outsiders cannot cheaply check that a result is reproducible, and a wrong or manipulated result can freeze a market or leave bad debt unprepared for.

1. **AI-generated risk analysis is unaccountable.** An agent can claim a loss figure at no cost if it is wrong.
2. **Risk results are hard to reproduce.** Conclusions are published, but inputs and computation are rarely committed in a form anyone can re-run.

## 2. Solution

A permissionless registry where an agent posts a **bonded stress-test claim** backed by a **retrievable, content-hashed case file**. A watcher agent fetches the file, verifies its hash, **recomputes the result from the committed snapshot**, and challenges a claim that does not reproduce. A designated resolver confirms the outcome and bonds move accordingly. A finalized claim can change controls on a mock lending market.

### What the watcher verifies, and what it does not

| The watcher verifies | The watcher does **not** verify |
|---|---|
| The retrieved case file hashes to the on-chain `evidenceHash` | That the snapshot is **complete** (no borrowers omitted) |
| The value claimed on-chain matches the value stated in the case file | That the snapshot **matches real chain state** at the pinned block |
| Recomputing the committed scenario on the committed snapshot with the pinned model reproduces the claimed residual bad debt exactly | That the model is realistic |
| The snapshot hash in the dataset manifest matches the snapshot | That a dataset labelled `REAL` truly is (it checks only the declared flag) |

So the watcher proves "this result is the correct output of these committed inputs," not "these inputs are the whole market." Snapshot completeness would require the watcher to re-extract the snapshot from an archive node at the pinned block and compare hashes. That is **post-MVP**, and no claim in the pitch or demo may imply it already exists.

The replayer is one shared reference module, so a bug in it would be shared by attester and watcher. The check proves reproducibility, not model correctness.

### What is model-driven and what is deterministic

| Component | Model-driven | Deterministic |
|---|---|---|
| Choosing the scenario (asset, shock size) | Yes, LLM with code-validated output (added after core flow) | |
| Plain-English finding and rationale | Yes | |
| Triage of suspicious claims | Yes, assist only | |
| Snapshot extraction from the Aave v3 fork | | Yes (pinned block, pinned script) |
| Loss computation from the snapshot | | Yes (integer math, pinned model) |
| Claim vs replay comparison and resolution inputs | | Yes |
| Bonds, windows, state transitions, vault trigger | | Yes (smart contracts) |

### Why bonds, if replay is deterministic?

Replaying costs compute and nobody does it for free. Bonds pay the watcher, make spam claims costly, and give the vault a claim it can act on only after it survives a challenge window.

## 3. Partner Alignment

Priorities 1 to 3 are real parts of the build. Priorities 4 to 7 come **after the core flow works**.

### 1. TigerGraph (graph database)

TigerGraph holds the exposure graph (ingestion pipeline in Section 6) and supplies scenario-selection context and the graph UI. **It is not in the verdict path:** the replay reads the snapshot file, never TigerGraph, so graph data cannot affect an on-chain outcome. Exposure estimates from graph queries are labelled "estimated exposure," never "bad debt."

### 2. AI Grants India Foundation (grants, narrative)

Application story: accountable AI agents for DeFi risk, built by an India-based team, as an open public-good layer. Check eligibility and process.

### 3. Socket (open-source security, cheap fit)

The agents hold private keys, so dependency supply-chain risk is real. Scan npm and Python dependencies, fix or pin flagged items, and show the result in the README or demo. Run it early. Confirm what Socket's bounty requires.

### 4. Flow (voice AI, stretch)

A voice-input product, not the Flow blockchain. A fitting use is a voice layer for the operator ("stress test a 30% ETH drop") or a spoken alert on challenge. Check what the sponsor expects.

### 5. Dodo Payments (payments, stretch)

A narrative for how protocols could pay for verified risk feeds. At most a small checkout demo. Check bounty requirements.

### 6. Cake Wallet (privacy wallet, weak fit, stretch)

First on the cut line unless a clean requirement appears.

### 7. Edge City India (community)

Community partner. No technical work.

## 4. System Overview

```
        Aave v3 mainnet fork (pinned block)
                    │ extract snapshot + reserve params
          ┌─────────▼──────────┐        ┌───────────────────┐
          │  Snapshot builder  │───────►│ TigerGraph loader │ (after core flow)
          └─────────┬──────────┘        └───────────────────┘
                    │ canonical snapshot.json
   ┌────────────────▼─────────────────────────────┐
   │              Backend (FastAPI)               │
   │  Replayer (static-liquidation-v1)            │
   │  Case-file builder + content-addressed store │
   │  Attester agent    Watcher agent    Resolver CLI │
   └───────┬──────────────────────────┬───────────┘
           │ postClaim / challenge    │ reads, events
   ┌───────▼──────────────────────────▼───────────┐
   │        Smart contracts (testnet)             │
   │  StressRegistry ──finalized──► DemoVault     │
   │                                  │           │
   │                          MockLendingMarket   │
   └───────────────────────┬──────────────────────┘
                           │ events, reads
                  ┌────────▼─────────┐
                  │ Frontend (Next.js)│
                  └──────────────────┘
```

### Two environments, kept separate

- **Analysis environment:** the Aave v3 mainnet fork supplies real positions and reserve parameters at a pinned block. The price shock is applied inside the replay model, not by swapping oracles. A fork-executed cross-check (override the oracle and call `liquidationCall` on a sample of accounts) is optional post-MVP hardening.
- **On-chain demo environment:** `StressRegistry`, `DemoVault` and a `MockLendingMarket` on a testnet.

State this split plainly: the fork produces the data, the mock market shows the on-chain consequence. Never imply the testnet vault controls real Aave.

## 5. Metrics and Replay Model

### 5.1 Metric definitions

These four terms are distinct and must be used exactly. "Bad debt" alone is never used for the other three.

| Term | Definition | Computed by replay | On-chain |
|---|---|---|---|
| **Liquidatable accounts** | Count of accounts with health factor below 1 at the shocked price | Yes | No (informational) |
| **Debt at risk** | Sum of debt held by liquidatable accounts | Yes | No (informational) |
| **Liquidation volume** | Sum of debt repaid by liquidators in the simulated liquidation pass | Yes | No (informational) |
| **Residual bad debt** | Debt left unrepaid after all collateral of liquidatable accounts is seized | Yes, under model `static-liquidation-v1` | **Yes: the adjudicated claim value** |

Reporting rule: report residual bad debt only from a run whose replay computed it. Graph-query estimates and any run that did not execute the model are labelled "estimated exposure."

### 5.2 Model `static-liquidation-v1`

All values are integers (USD with 8 decimals, matching Aave's base-currency precision). No floating point.

```
shockedPrice    = price * (10000 + shockBps) / 10000          # floor; shockBps in [-9000, 0)
collateralValue = collateralAmount * shockedPrice / 10**decimals   # floor
liquidatable    = collateralValue * ltBps / 10000 < debt      # health factor < 1
repaid          = min(debt, collateralValue * 10000 / bonusBps)    # bonusBps e.g. 10500
residualBadDebt = debt - repaid                               # per liquidatable account
```

Totals: `liquidatableAccounts` = count, `debtAtRisk` = Σ debt, `liquidationVolume` = Σ repaid, `residualBadDebt` = Σ (debt − repaid), all over liquidatable accounts.

**Stated assumptions (shown in the UI and the case file):**

- One collateral asset per account (the shocked asset). Debt is the account's total debt in USD from the snapshot and is not shocked.
- One liquidation pass, full liquidation (close factor 100%) at the shocked oracle price.
- No slippage or price impact, no liquidator capacity or gas limits, no delay, no liquidation protocol fee, no interest accrual after the pinned block.
- **This is not a multi-round cascade.** Price-impact feedback is out of scope, so the earlier "cascade" wording is replaced by "liquidation simulation."
- The result is an estimate under these assumptions, not a forecast of real Aave losses.

### 5.3 Snapshot scope filter

To fit the model, the snapshot includes only accounts whose collateral is exclusively the shocked asset (WETH), with stablecoin debt, outside eMode and isolation mode. The filter is recorded in the manifest. The result therefore covers **that subset of Aave borrowers**, not the whole market, and must never be described as market-wide bad debt.

## 6. Data Pipeline: Pinned Dataset to TigerGraph

### 6.1 Dataset classes

Every account carries an `origin`, and the dataset carries a `dataClass`:

| `origin` | Meaning |
|---|---|
| `real_aave_v3_fork` | Extracted from the Aave v3 mainnet fork at the pinned block |
| `synthetic` | Generated by a seeded script. Uses ids like `synth-0001`, never addresses |

| `dataClass` | Rule |
|---|---|
| `REAL` | All accounts real |
| `MIXED` | Contains any synthetic account. Synthetic accounts may be added only to make demo concentration visible |
| `SYNTHETIC` | All synthetic. Fallback if fork extraction fails |

The UI shows a visible banner for `MIXED` and `SYNTHETIC`. A result from non-`REAL` data must never be presented as describing real Aave. `dataClass` is inside the case file, so it is covered by `evidenceHash`.

### 6.2 Pipeline

| Step | Action | Output |
|---|---|---|
| 1. Pin | Choose fork block `N` and record the network, Pool, data provider and oracle addresses, script git commit, and synthetic seed | `dataset_manifest.json` (draft) |
| 2. Extract real | At block `N`, collect borrower addresses from `Borrow` events up to `N`. For each, read account and per-reserve data (for example `getUserAccountData` and the protocol data provider's `getUserReserveData`) and the WETH reserve configuration. Apply the Section 5.3 filter | `real_accounts.jsonl` |
| 3. Generate synthetic (optional) | Seeded generator adds clearly flagged accounts | `synthetic_accounts.jsonl` |
| 4. Normalize | Merge, convert to integers, sort by id, serialize canonically, compute `snapshotHash` | `snapshot.json`, final manifest with counts and hashes |
| 5. Load into TigerGraph | Upsert from `snapshot.json` (pyTigerGraph or a loading job). The load is idempotent | Graph populated |
| 6. Reconcile | Query the graph for vertex counts and collateral and debt totals. Compare with the manifest. **Fail loudly on any mismatch** | Reconciliation report |

Function names above are illustrative. Confirm them against the deployed Aave v3 ABI.

**Manifest fields (minimum):**

```json
{
  "datasetId": "weth-stable-<block>-v1",
  "dataClass": "REAL",
  "network": "ethereum-mainnet-fork",
  "forkBlock": 0,
  "poolAddress": "0x...",
  "dataProviderAddress": "0x...",
  "oracleAddress": "0x...",
  "extractionScriptCommit": "<git sha>",
  "syntheticSeed": null,
  "filter": "collateral=WETH only; debt=stablecoins; eMode=0; isolation=false",
  "counts": { "real": 0, "synthetic": 0 },
  "snapshotHash": "0x...",
  "extractedAt": "ISO-8601"
}
```

Do not store RPC URLs or keys in the manifest. Record the provider name only.

### 6.3 TigerGraph schema (illustrative)

```
VERTEX Account  (id STRING, origin STRING, debt_usd8 UINT, collateral_usd8 UINT,
                 dataset_id STRING, snapshot_hash STRING, fork_block UINT)
VERTEX Asset    (symbol STRING, price_usd8 UINT, lt_bps UINT, bonus_bps UINT)
VERTEX Dataset  (dataset_id STRING, data_class STRING, snapshot_hash STRING)
EDGE   COLLATERAL_IN (Account -> Asset, amount STRING)
EDGE   INCLUDED_IN   (Account -> Dataset)
```

Every vertex keeps `origin`, `dataset_id` and `snapshot_hash`, so any graph result can be traced to a pinned snapshot and filtered by real versus synthetic.

**Uses (after the core flow):** scenario-selection queries (for example, accounts closest to liquidation, concentration of debt in the top N accounts) feeding the attester's LLM as structured context, and the UI graph colored from replay output.

## 7. End-to-End Flow

1. **Snapshot.** Build and pin the dataset (Section 6, steps 1 to 4).
2. **Scenario.** Phase 1: fixed config (asset, `shockBps`). Later: TigerGraph queries plus LLM propose it, with code-validated parameters.
3. **Replay.** The replayer computes the four metrics and per-account outcomes.
4. **Case file.** Build the case file (schema below), serialize canonically, compute `evidenceHash = keccak256(bytes)`, and store it in a content-addressed location. Obtain `caseFileURI`.
5. **Claim.** The attester calls `postClaim(...)` with the bond, including `caseFileURI`, `evidenceHash` and `claimedResidualBadDebt`.
6. **Independent replay.** The watcher reads the `ClaimPosted` event, then:
   1. fetches the file at `caseFileURI`
   2. computes `keccak256` of the fetched bytes and **compares it with the on-chain `evidenceHash`. If it differs or the file cannot be fetched, the watcher does not replay**
   3. checks the claimed on-chain value equals the file's `residualBadDebtUsd8`
   4. recomputes from the file's own snapshot, scenario and model
   5. compares exactly with the claim
7. **Challenge.** On a mismatch (or invalid evidence), the watcher posts `challenge(...)` with its own bond and a replay report.
8. **Resolution.** The designated resolver repeats the checks (Resolver CLI) and calls `resolve(...)`. Bonds move per Section 8.4.
9. **Effect.** After a claim is `Finalized`, anyone calls `DemoVault.applyClaim(claimId)`, which changes controls on the mock market.

### Case-file schema (minimum)

```json
{
  "schemaVersion": 1,
  "marketId": "aave-v3-eth-weth-stable",
  "dataClass": "REAL",
  "dataset": { "...manifest fields...": "" },
  "snapshot": {
    "assets": { "WETH": { "decimals": 18, "priceUsd8": "0", "ltBps": 0, "bonusBps": 0 } },
    "accounts": [ { "id": "0x...", "origin": "real_aave_v3_fork", "collateralAmount": "0", "debtUsd8": "0" } ]
  },
  "scenario": { "asset": "WETH", "shockBps": -3000 },
  "agentRationale": "...",
  "model": { "id": "static-liquidation-v1", "replayerCommit": "<git sha>" },
  "results": {
    "liquidatableAccounts": 0,
    "debtAtRiskUsd8": "0",
    "liquidationVolumeUsd8": "0",
    "residualBadDebtUsd8": "0"
  }
}
```

**Canonical serialization:** UTF-8 JSON, keys sorted, no whitespace, integers only (large values as decimal strings), arrays in the order defined (accounts sorted by `id`). The scenario and the agent's rationale are inside the file, so `evidenceHash` already commits to them.

**Storage:** `caseFileURI` is `ipfs://<CID>` where a pinning service is available, with the backend serving `GET /case-files/{evidenceHash}` as a fallback. Either way the watcher verifies the keccak256 hash, so the transport does not need to be trusted. Pin the file before posting the claim.

## 8. Smart Contracts (Person A)

### 8.1 `StressRegistry` interface

```
postClaim(marketId, claimedResidualBadDebt, evidenceHash, caseFileURI) payable returns (claimId)
challenge(claimId, reason, counterResidualBadDebt, replayReportURI, replayReportHash) payable
resolve(claimId, challengeUpheld)               // resolver only
finalize(claimId)                               // anyone, unchallenged claims after the window
expireUnresolved(claimId)                       // anyone, after the resolution deadline
withdraw()                                      // pull payments
status(claimId), claim(claimId)                 // reads
```

`reason` is `WRONG_RESULT` or `EVIDENCE_INVALID` (file unretrievable or hash mismatch). For `EVIDENCE_INVALID`, `counterResidualBadDebt` is ignored.

**Constants (set in the constructor, demo values on testnet):**

| Constant | MVP value | Note |
|---|---|---|
| `BOND` | 0.01 ETH, same for attester and challenger | Fixed. No scaling |
| `CHALLENGE_WINDOW` | 120 seconds | Short for the demo. Production would be hours or days |
| `RESOLUTION_WINDOW` | 300 seconds | Time the resolver has once a challenge exists |
| `TOLERANCE_BPS` | 0 | Replay is integer math on a shared pinned module, so exact match is expected |
| `resolver` | Set at deployment, immutable | A multisig or a single wallet |

### 8.2 Claim states

`None`, `Pending`, `Challenged`, `Finalized`, `Rejected`, `Expired`. The last three are terminal. **Only `Finalized` enables the vault.**

### 8.3 Transitions

| From | Call | Caller | Conditions | To | Effects |
|---|---|---|---|---|---|
| `None` | `postClaim` | Anyone | `msg.value == BOND`, non-zero `evidenceHash`, non-empty `caseFileURI` | `Pending` | Stores claim, sets `challengeDeadline = now + CHALLENGE_WINDOW`, emits `ClaimPosted` |
| `Pending` | `challenge` | Anyone except the attester | `now < challengeDeadline`, `msg.value == BOND`, one challenge only, non-zero `replayReportHash`, and for `WRONG_RESULT` `counterResidualBadDebt != claimedResidualBadDebt` | `Challenged` | Stores challenger and report, sets `resolutionDeadline = now + RESOLUTION_WINDOW`, emits `ClaimChallenged` |
| `Pending` | `finalize` | Anyone | `now >= challengeDeadline`, no challenge | `Finalized` | Credits attester `BOND`, emits `ClaimFinalized` |
| `Challenged` | `resolve(false)` | Resolver | `now < resolutionDeadline`, resolver is neither attester nor challenger | `Finalized` | Challenge unsuccessful. Credits attester `2 × BOND` |
| `Challenged` | `resolve(true)` | Resolver | same conditions | `Rejected` | Challenge upheld. Credits challenger `2 × BOND` |
| `Challenged` | `expireUnresolved` | Anyone | `now >= resolutionDeadline` | `Expired` | Credits attester `BOND` and challenger `BOND` |

The challenge window and resolution window use strict `<` and `>=` so there is no moment when two transitions are both valid.

### 8.4 Bond distribution

| Scenario | Final state | Attester receives | Challenger receives |
|---|---|---|---|
| Honest claim, no challenge | `Finalized` | `BOND` (own bond back) | none |
| Honest claim, unsuccessful challenge | `Finalized` | `2 × BOND` (own plus the challenger's) | `0` (loses bond) |
| Incorrect claim, successful challenge | `Rejected` | `0` (loses bond) | `2 × BOND` (own plus the attester's) |
| Challenged, resolver does not act in time | `Expired` | `BOND` | `BOND` |

No protocol fee and no treasury in the MVP. Payouts are credited to an internal balance and claimed with `withdraw()` (pull pattern, avoids reentrancy during payout).

### 8.5 Resolver permissions

| The resolver can | The resolver cannot |
|---|---|
| Call `resolve` on a `Challenged` claim before `resolutionDeadline` | Resolve a `Pending` claim |
| Decide only `challengeUpheld` true or false | Resolve after the deadline, or resolve a claim it posted or challenged |
| | Change bonds, windows, tolerance, or the resolver address |
| | Finalize a claim that was never posted or challenged without the window elapsing |
| | Withdraw anyone else's credited balance |

**Resolver procedure (off-chain, via Resolver CLI):** fetch the file at `caseFileURI` (or the challenger's cached copy), verify the hash, replay, compare. Uphold the challenge if the evidence is invalid or unretrievable, or if the recomputed residual bad debt differs from the claim. This is the trusted step in the MVP, and it must be disclosed as such.

### 8.6 Events

| Event | Fields |
|---|---|
| `ClaimPosted` | `claimId`, `attester`, `marketId`, `claimedResidualBadDebt`, `evidenceHash`, `caseFileURI`, `challengeDeadline` |
| `ClaimChallenged` | `claimId`, `challenger`, `reason`, `counterResidualBadDebt`, `replayReportURI`, `replayReportHash`, `resolutionDeadline` |
| `ClaimResolved` | `claimId`, `challengeUpheld`, `winner`, `amountCredited` |
| `ClaimFinalized` | `claimId` |
| `ClaimExpired` | `claimId` |
| `Withdrawn` | `account`, `amount` |

### 8.7 `DemoVault` and `MockLendingMarket`

- `applyClaim(claimId)`: callable by anyone. Requires `status == Finalized`, the claim's `marketId` matches the vault's market, and the claim has not been applied.
- Fixed rule: if `claimedResidualBadDebt >= PAUSE_THRESHOLD`, set `borrowPaused = true`. Else if `>= LTV_THRESHOLD`, set `maxLtvBps = REDUCED_LTV_BPS`. Else revert `BelowThreshold`.
- `resetControls()`: owner only, so the demo can be repeated.
- `MockLendingMarket.borrow(...)` consults the vault and reverts when paused or when the requested LTV exceeds `maxLtvBps`.
- A `Rejected` or `Expired` claim cannot be applied.

### 8.8 Known limitations of the MVP contracts

- **Fixed bond.** A cheap bond does not scale with the size of the claim, so griefing is not solved by economics. In the MVP it is limited by: only `Finalized` claims act, the vault changes are bounded to preset values, and the target is a mock market.
- **Unwatched incorrect claims finalize.** The security model needs at least one active watcher.
- **Resolver is trusted** and could be wrong or unavailable (the `Expired` path covers unavailability).

## 9. Backend and Agents (Person B)

| Interface | Purpose |
|---|---|
| `POST /stress/run` | Builds snapshot reference, runs the replayer, builds and stores the case file, returns `evidenceHash` and `caseFileURI` |
| `GET /case-files/{evidenceHash}` | Content-addressed fetch (fallback transport) |
| `GET /graph/exposure` | Exposure graph data from TigerGraph (after core flow) |

**Replayer:** pure function `replay(case_file) -> report`, integer math, no network access, pinned by git commit. The report contains the four metrics and per-account outcomes (`liquidatable`, `repaid`, `residual`).

**Attester agent:** Phase 1 runs a fixed scenario config and posts the claim. After the core flow it adds TigerGraph queries and the LLM scenario proposal.

**Watcher agent:** subscribes to `ClaimPosted`, runs the Section 7 step-6 checks, stores a replay report (content-addressed like the case file), and calls `challenge` on a mismatch or invalid evidence. Collects the payout through `withdraw()`.

**Resolver CLI:** given a `claimId`, fetches the claim and report, repeats the checks, prints the verdict, and sends `resolve` from the resolver wallet after confirmation.

**Malicious attester script:** see Section 11.

## 10. Frontend (Person C)

Stack: Next.js, wagmi/viem, RainbowKit, Tailwind, shadcn/ui, react-force-graph or Cytoscape.js.

| Screen | Content |
|---|---|
| **Markets** | Market list with claim status, last result, vault state, wallet connect |
| **Stress Test** | Scenario controls, results showing the four metrics with their exact names, assumptions panel, data-class banner, case-file hash and URI, Publish claim |
| **Claims** | Table with ID, attester, claimed residual bad debt, bond, status, deadlines, `caseFileURI`, with Challenge, Finalize and Verify actions, and live status chips |
| **Verify and Vault** | In-browser fetch and keccak256 check against `evidenceHash`, vault panel (max LTV, paused, triggering claim), "Try borrow" showing the revert |
| **Agent feed** | Events: attester posted, watcher replayed, watcher challenged, resolver decided, bonds moved |
| **Graph (after core flow)** | TigerGraph exposure graph, accounts colored from replay output |

## 11. Demo Script

1. State the problem in one sentence. Name Chaos Labs, Gauntlet, UMA and opML as related work.
2. State the scope up front: the data comes from the Aave v3 fork at a pinned block (show `dataClass`), and the on-chain effect happens on a mock market.
3. **Honest claim:** the attester replays a scenario, builds the case file, posts a claim. Show the `ClaimPosted` event with `caseFileURI` and `evidenceHash`.
4. The watcher fetches the file, verifies the hash, replays, and the numbers match. No challenge. After the window the claim finalizes, the vault applies it, and "Try borrow" reverts.
5. **Dishonest claim:** run the malicious attester (below). The watcher fetches, verifies the hash (it passes), replays, and sees a different residual bad debt. Show the two numbers side by side, the challenge, the resolver's decision, and the bond transfer to the watcher.
6. Show that the rejected claim cannot be applied to the vault.
7. Close on what is model-driven versus verified, and name the trusted resolver and the unverified snapshot completeness.

### Malicious attester (MVP behaviour)

The script takes the honest case file, **keeps the snapshot and scenario unchanged**, inflates `results.residualBadDebtUsd8` (for example, triples it), recomputes the file hash, stores the file, and posts a claim with the inflated value. The evidence is retrievable and hash-consistent, but the claimed result does not reproduce from the same committed snapshot. This is the only dishonest behaviour the MVP demonstrates. **Do not demo omitted borrowers or a stale block as something the watcher catches**, because the watcher does not check snapshot completeness or chain state.

Label staged parts: scripted dishonest attester, designated resolver, mock market, short windows.

## 12. Design Decisions and Answers to Likely Judge Questions

| Question | Answer |
|---|---|
| **What does the watcher actually check?** | That the case file matches its on-chain hash and that the claimed residual bad debt is the exact output of the committed snapshot, scenario and model. See the table in Section 2 |
| **What if the attester omits risky borrowers?** | Not detected in the MVP. The watcher checks the computation, not completeness. A watcher that re-extracts the snapshot from an archive node at the pinned block and compares hashes would detect it. That is future work |
| **Is the data real?** | Every account is flagged `real_aave_v3_fork` or `synthetic`, and the case file carries a `dataClass`. The model covers a filtered subset of borrowers, not the whole market |
| **Is "bad debt" real?** | It is residual bad debt under a stated static model: one liquidation pass, no slippage, no price impact. It is not a forecast and not a multi-round cascade |
| **Why a designated resolver?** | MVP stand-in. The resolver's inputs are mechanical (hash check and replay). Production: UMA or similar, with multiple independent replayers |
| **Can someone grief the vault with a cheap bond?** | The bond is fixed in the MVP, so economics alone do not stop it. Mitigations: only finalized claims act, vault changes are bounded presets, and the target is a mock market. Bond scaling is future work |
| **Is replay deterministic?** | Yes by construction: integer math on a committed file with a pinned replayer commit, and an exact-match rule. Shared code means shared bugs |
| **What if the case file is unavailable?** | The watcher does not replay and can challenge with `EVIDENCE_INVALID`. The resolver decides |
| **Why bonds?** | They pay watchers for compute, deter spam, and let the vault act only on claims that survived a window |
| **Why a blockchain?** | Bonds, a public tamper-evident claim record with content-addressed evidence, and a trigger the vault can consume |
| **Why not UMA?** | UMA resolves open-ended questions by token-holder vote. These claims can be recomputed from committed inputs. UMA can be the production resolver |
| **Why not Chaos Labs?** | They are a single trusted provider. This makes a result reproducible by anyone |
| **Why not opML, Cortex, Warden, Horus?** | They target general AI inference or reasoning. This is a specific lending-risk workflow with a replayable evidence trail and a vault consumer |
| **Where is the AI?** | Scenario choice, findings and triage, added after the core flow. The verdict is deliberately deterministic, so the AI is a proposer, not a judge |
| **Is the demo live?** | State plainly: scripted dishonest attester, designated resolver, mock market, short windows |

## 13. Prior Art (name it first)

| Area | Existing work |
|---|---|
| Risk oracle changing lending parameters | Chaos Labs Edge Risk Oracles, live on Aave |
| Fork-based protocol simulation | Chaos Labs simulation platform |
| Public ETH-shock simulations for Aave | Independent liquidation risk analyses on the Aave governance forum |
| Per-wallet "what if collateral drops" for agents | alertio MCP `simulate_liquidation` |
| Open-source cascade simulators | Crypto-Lending-Risk-Simulator (off-chain only) |
| Bonded claim with dispute and slashing | UMA optimistic oracle |
| Optimistic verification of AI output | opML (ORA) |
| Bonded AI reasoning and challenge markets | Cortex Protocol, Horus, Warden, Courtside (ETHGlobal New York 2026) |
| Stake-backed agent attestations | Symbiotic Relay SDK, ChaosChain Triple-Verified Stack |
| Safety attestations for DeFi agents | Aegis (The Synthesis hackathon) |

**Position:** a new combination of existing parts, not a "first." Bonded, challengeable AI is already crowded, so lead with the lending-risk workflow, the reproducible case file, and the vault consequence. Avoid "first", "novel" and "only."

**Verify before putting on a slide:** the Chaos Labs exit from Aave's risk role (one article), the claim that Chaos Labs' closed Edge calculations limit independent verification (one secondary source), the "Cournot" project and a specific Aave liquidation-capacity post cited by another reviewer (not located), and ETHGlobal and Devfolio showcases by keyword (not searched).

## 14. Timeline (40 hours)

**Phase 1: core flow (target: hour 24).** Nothing else starts until this passes.

| Hours | Person A | Person B | Person C |
|---|---|---|---|
| **0 to 8** | `StressRegistry` states and transitions, `MockLendingMarket`, deploy script | Pin dataset, snapshot builder from the fork, canonical serializer | Scaffold, wallet connect, read a claim |
| **8 to 16** | Bond payouts, `withdraw`, `DemoVault`, state-machine tests (all rows of 8.3 and 8.4) | Replayer, case-file builder, content-addressed storage, attester posts a claim | Claims table with Publish, Challenge, Finalize |
| **16 to 24** | Event polish, malicious-attester support | Watcher (fetch, hash check, replay, challenge), Resolver CLI, malicious attester | Verify screen, vault panel with "Try borrow" |

**Phase 2: layered features (hours 24 to 34).** TigerGraph load and reconciliation, scenario queries, LLM scenario proposal and rationale, exposure graph, agent feed. Run the Socket scan.

**Phase 3: polish and extras (hours 34 to 40).** Demo rehearsal, assumptions panel, then any stretch partner item that is cheap.

**Hour 24 checkpoint:** if the Phase 1 flow does not pass end to end, stop Phase 2 work and fix it.

## 15. Cut Line

Drop in this order:

1. Cake Wallet
2. Dodo Payments
3. Flow voice layer
4. LLM triage and summaries
5. Graph animation (use a static colored graph)
6. TigerGraph-driven scenario selection (use a fixed scenario, keep the graph display)
7. In-browser hash check (use a CLI)

**Never cut:** the Section 0 flow, hash verification before replay, the state machine with correct bond transfers, the data-class labelling, the Socket scan.

## 16. Setup Checklist

- [ ] Read each partner's bounty requirements on the Hacker House Goa page
- [ ] Choose a testnet (no partner chain requirement is visible)
- [ ] Fund at least four wallets with testnet ETH: attester, watcher/challenger, resolver, deployer
- [ ] Pick the fork block `N`, and confirm the extraction filter yields enough accounts
- [ ] Decide the case-file transport (IPFS pinning service, or backend only)
- [ ] Set up TigerGraph (Phase 2) and the loader
- [ ] Pick an LLM provider and confirm limits (Phase 2)
- [ ] Write and run state-machine tests for every transition and payout
- [ ] Run a Socket scan on the repo
- [ ] Search ETHGlobal and Devfolio manually for similar projects

## 17. Risks

| Risk | Mitigation |
|---|---|
| Scope | Phase 1 gate at hour 24 and the cut line |
| Too few real accounts after the filter | Allow flagged synthetic accounts (`MIXED`), with a banner. Fallback `SYNTHETIC` |
| Judges read the result as real Aave bad debt | Metric definitions, assumptions panel, `dataClass` banner, subset wording |
| Judges ask about omitted borrowers | Answer from Section 12: not checked in the MVP |
| Case file unavailable at demo time | Pin early, keep the backend fallback and a local copy |
| Resolver unavailable | `Expired` path refunds both bonds |
| Unwatched incorrect claim | Keep the watcher running, and disclose the dependency |
| Overclaiming | Label staged parts, name incumbents, avoid "first" and "unique" |

## 18. One-Paragraph Pitch

DeFi protocols already act on risk analysis they cannot verify, and AI agents are about to produce more of it. StressProof makes that analysis accountable: an agent computes a stress-test result from a pinned Aave v3 snapshot, publishes the case file and posts the result as a bonded claim. A watcher agent verifies the file's hash, recomputes the result independently, and challenges anything that does not reproduce, earning the other side's bond. Claims that survive the window can tighten controls on a lending market. The model proposes, and reproducible computation and economics decide. The snapshot's completeness and the resolver's honesty are the next trust assumptions to remove.
