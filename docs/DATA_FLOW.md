# StressProof: End-to-End System Data Flow

This document details the precise data transformations, byte-level flows, network boundaries, and state transitions across the StressProof architecture.

---

## 1. High-Level Data Journey

```mermaid
flowchart TD
    subgraph Phase1["1. Scenario & Generation"]
        AaveFork["Aave v3 Archive Snapshot (Block N)"] --> RawData["Raw Borrower Data"]
        RawData --> Normalizer["Pipeline Normalizer (synth.py / normalize.py)"]
        Normalizer --> Snapshot["snapshot.json + manifest.json"]
        ScenarioInput["Scenario Input (WETH, -3000 bps)"] --> Backend["FastAPI POST /stress/run"]
        Snapshot --> Backend
    end

    subgraph Phase2["2. Replay & Content Commitment"]
        Backend --> CoreReplay["Pure Core Replayer (static-liquidation-v1)"]
        CoreReplay --> CaseFile["Case File JSON (Schema v1)"]
        CaseFile --> Canonicalizer["Canonical JSON Serializer"]
        Canonicalizer --> RawBytes["Canonical UTF-8 Bytes"]
        RawBytes --> Keccak["Keccak-256 Hashing"]
        Keccak --> EvidenceHash["evidenceHash (bytes32 hex)"]
        RawBytes --> Store["ContentStore: data/case-files/{hash}.json"]
    end

    subgraph Phase3["3. On-Chain Bonded Attestation"]
        EvidenceHash --> AttesterAgent["Attester Agent"]
        AttesterAgent --> PostTx["StressRegistry.postClaim() + 0.01 ETH"]
        PostTx --> Registry["StressRegistry (State: Pending)"]
        Registry --> Event["Emit ClaimPosted(id, evidenceHash, ...)"]
    end

    subgraph Phase4["4. Independent Audit & Challenge"]
        Event --> Watcher["Watcher Daemon"]
        Watcher --> Fetch["GET /case-files/{evidenceHash}"]
        Fetch --> VerifyHash{"keccak256(bytes) == evidenceHash?"}
        VerifyHash -- Yes --> CoreReplay2["Run Core Replay"]
        VerifyHash -- No --> InvalidFlow["Challenge EVIDENCE_INVALID"]
        CoreReplay2 --> CheckMatch{"Replayed Residual == Claimed Residual?"}
        CheckMatch -- Disagree --> ChallengeFlow["Challenge WRONG_RESULT"]
        CheckMatch -- Agree --> HonestFlow["Stay Silent (Verdict: MATCH)"]
    end

    subgraph Phase5["5. Resolution & Settlement"]
        ChallengeFlow --> ChallengeTx["StressRegistry.challenge() + 0.01 ETH"]
        ChallengeTx --> ChallengedState["State: Challenged"]
        ChallengedState --> Resolver["Resolver CLI (replays evidence)"]
        Resolver --> ResolveTx["StressRegistry.resolve(id, upheld)"]
        ResolveTx --> Settlement["Credits Winner 2x BOND (0.02 ETH)"]
    end

    subgraph Phase6["6. Finalization & Vault Defense"]
        HonestFlow --> WaitWindow["Wait 120s Challenge Window"]
        WaitWindow --> FinalizeTx["StressRegistry.finalize(id)"]
        FinalizeTx --> FinalState["State: Finalized"]
        FinalState --> ApplyTx["DemoVault.applyClaim(id)"]
        ApplyTx --> LtvUpdate["DemoVault: maxLtvBps 80% -> 50%"]
        LtvUpdate --> Market["MockLendingMarket: Reverts Borrows > 50% LTV"]
    end
```

---

## 2. Data Flow 1: Offline Snapshot Generation & Normalization

```mermaid
sequenceDiagram
    autonumber
    participant RPC as Mainnet Archive Node
    participant Pin as extraction.pin
    participant Extract as extraction.extract
    participant Norm as normalization.normalize
    participant Storage as data/fixtures/datasets/

    Pin->>RPC: Read Block N Header, Pool Address, Oracle Address
    Pin->>Pin: Define stablecoin allowlist & WETH address
    Pin->>Storage: Write draft dataset_manifest.json
    Extract->>RPC: eth_getLogs(Aave Pool, Borrow events, block N-M to N)
    RPC-->>Extract: Unique borrower addresses
    Extract->>RPC: Multicall3: getUserAccountData(user) at Block N
    RPC-->>Extract: Collateral (ETH) and Debt (USD) balances
    Extract->>Norm: Filter: single-collateral WETH, stablecoin debt, no eMode
    Norm->>Norm: Sort accounts ascending by ID
    Norm->>Norm: Compute canonical JSON snapshot bytes
    Norm->>Norm: snapshotHash = keccak256(canonical_bytes)
    Norm->>Storage: Store canonical snapshot.json & finalized dataset_manifest.json
```

---

## 3. Data Flow 2: Simulation Execution & Content-Addressed Storage

```mermaid
sequenceDiagram
    autonumber
    actor Client as Frontend UI / Attester
    participant BFF as Next.js API (/api/stress/run)
    participant FastAPI as Backend (/stress/run)
    participant Core as stressproof_core
    participant Disk as Filesystem / Postgres

    Client->>BFF: POST {datasetId: "weth-stable-fixture-v1", scenario: {shockBps: -3000}}
    BFF->>BFF: Validate payload shape & apply IP rate limiting (30 req/min)
    BFF->>FastAPI: POST /stress/run (Header: Bearer $API_WRITE_TOKEN)
    FastAPI->>FastAPI: Verify Bearer token against settings.API_WRITE_TOKEN
    FastAPI->>FastAPI: Load dataset snapshot from DatasetRegistry
    FastAPI->>Core: build_case_file(snapshot, manifest, scenario)
    Core->>Core: replay(case_file) -> Calculate bad debt totals
    Core-->>FastAPI: Complete case_file dict with results
    FastAPI->>Core: canonical_bytes(case_file)
    Core-->>FastAPI: Raw UTF-8 bytes
    FastAPI->>Core: keccak256_hex(bytes) -> evidenceHash
    FastAPI->>Disk: Store case file at data/case-files/{evidenceHash}.json
    FastAPI->>Disk: Store per-account outcomes at data/replay_outputs/{evidenceHash}.jsonl
    FastAPI->>Disk: Append event to data/feed.jsonl
    FastAPI-->>BFF: Return {evidenceHash, caseFileURI, results}
    BFF-->>Client: Return JSON response
```

---

## 4. Data Flow 3: Bonded Attestation & On-Chain Event Propagation

```mermaid
sequenceDiagram
    autonumber
    actor Attester as Attester Agent / Wallet
    participant Registry as StressRegistry.sol
    participant Mempool as EVM Node / Anvil (Chain 31337)
    participant Watcher as Watcher Daemon

    Attester->>Attester: Simulate postClaim with eth_call
    Attester->>Mempool: Broadcast tx: postClaim(marketId, claimedResidual, evidenceHash, uri)
    Note over Attester,Mempool: msg.value == 0.01 ETH (BOND)
    Mempool->>Registry: Execute postClaim()
    Registry->>Registry: Assert msg.value == BOND
    Registry->>Registry: totalLocked += 0.01 ETH
    Registry->>Registry: claimCount++
    Registry->>Registry: Store Claim struct (state: Pending, deadline: now + 120s)
    Registry-->>Mempool: Emit ClaimPosted(claimId, attester, marketId, claimedResidual, evidenceHash, uri, deadline)
    Mempool-->>Watcher: New log event via eth_getLogs / WebSocket
```

---

## 5. Data Flow 4: Watcher Verification & Replay Engine

```mermaid
sequenceDiagram
    autonumber
    participant Watcher as Watcher Daemon
    participant Fetcher as SSRF EvidenceFetcher
    participant Backend as ContentStore / Gateway
    participant Core as stressproof_core
    participant State as SQLite WatcherState

    Watcher->>State: Check if claimId already processed
    Watcher->>Fetcher: fetch(claim.caseFileURI)
    Fetcher->>Fetcher: Validate URI (HTTPS / localhost, no RFC 1918, size < 25MB)
    Fetcher->>Backend: HTTP GET request (no redirects)
    Backend-->>Fetcher: Raw byte stream
    Fetcher-->>Watcher: Raw bytes
    Watcher->>Core: keccak256_hex(rawBytes)
    alt Hash != onchain.evidenceHash
        Watcher->>Watcher: Flag HASH_MISMATCH -> Verdict: EVIDENCE_INVALID
    else Hash == onchain.evidenceHash
        Watcher->>Core: validate(rawBytes, onchain)
        alt Structural Violation (V-01..V-13)
            Watcher->>Watcher: Verdict: EVIDENCE_INVALID
        else Valid Structure
            Watcher->>Core: replay(case_file)
            alt Replayed Residual != onchain.claimedResidualBadDebt
                Watcher->>Watcher: Verdict: WRONG_RESULT (counter = replayed)
            else Replayed Residual == onchain.claimedResidualBadDebt
                Watcher->>Watcher: Verdict: MATCH (Honest Claim)
            end
        end
    end
    Watcher->>State: Record verdict and update local SQLite state
```

---

## 6. Data Flow 5: Challenge Submission & Dispute Settlement

```mermaid
sequenceDiagram
    autonumber
    actor Challenger as Watcher / Challenger Wallet
    participant Registry as StressRegistry.sol
    actor Resolver as Designated Resolver
    participant Core as stressproof_core (Resolver Local)

    Note over Challenger,Registry: When Verdict != MATCH
    Challenger->>Registry: challenge(claimId, reason, counterResidual, reportURI, reportHash)
    Note over Challenger,Registry: msg.value == 0.01 ETH (BOND)
    Registry->>Registry: Assert state == Pending && now < challengeDeadline
    Registry->>Registry: totalLocked += 0.01 ETH (total 0.02 ETH locked)
    Registry->>Registry: state = Challenged, resolutionDeadline = now + 300s
    Registry-->>Challenger: Emit ClaimChallenged

    Note over Resolver,Registry: Dispute Phase
    Resolver->>Registry: Read claim data (evidenceHash, caseFileURI)
    Resolver->>Resolver: Fetch evidence and run local stressproof_core.evaluate()
    alt Evidence Invalid or Replayed != Claim
        Resolver->>Registry: resolve(claimId, upheld = true)
        Registry->>Registry: state = Rejected
        Registry->>Registry: totalLocked -= 0.02 ETH, credits[challenger] += 0.02 ETH
        Registry-->>Resolver: Emit ClaimResolved(claimId, true, challenger, 0.02 ETH)
    else Evidence Valid and Replayed == Claim
        Resolver->>Registry: resolve(claimId, upheld = false)
        Registry->>Registry: state = Finalized
        Registry->>Registry: totalLocked -= 0.02 ETH, credits[attester] += 0.02 ETH
        Registry-->>Resolver: Emit ClaimResolved(claimId, false, attester, 0.02 ETH)
    end
```

---

## 7. Data Flow 6: Vault Defense & Borrow Execution

```mermaid
sequenceDiagram
    autonumber
    actor Caller as Any User / Automation
    participant Registry as StressRegistry.sol
    participant Vault as DemoVault.sol
    actor Borrower as Borrower Account
    participant Market as MockLendingMarket.sol

    Caller->>Vault: applyClaim(claimId)
    Vault->>Registry: claim(claimId)
    Registry-->>Vault: Return Claim struct
    Vault->>Vault: Assert claim.state == Finalized
    Vault->>Vault: Assert claim.marketId == MARKET_ID
    Vault->>Vault: Assert applied[claimId] == false
    alt claimedResidualBadDebt >= $4,000 (PAUSE_THRESHOLD)
        Vault->>Vault: borrowPaused = true
    else claimedResidualBadDebt >= $1,000 (LTV_THRESHOLD)
        Vault->>Vault: maxLtvBps = REDUCED_LTV_BPS (50%)
    end
    Vault->>Vault: applied[claimId] = true
    Vault-->>Caller: Emit ClaimApplied(claimId, residual, paused, maxLtvBps)

    Note over Borrower,Market: Borrower Interaction
    Borrower->>Market: borrow(collateralUsd8 = 10,000, amountUsd8 = 7,000) [70% LTV]
    Market->>Vault: borrowPaused()
    Vault-->>Market: false
    Market->>Vault: maxLtvBps()
    Vault-->>Market: 5000 (50%)
    Market->>Market: Calculate requested LTV = 7000 bps
    Market-->>Borrower: REVERT LtvTooHigh(7000, 5000)
```

---

## 8. Data Flow 7: Client-Side Replay Graph Rendering & Audit

```mermaid
sequenceDiagram
    autonumber
    actor User as Browser User
    participant Page as /graph Page
    participant Loader as graph/loader.ts
    participant Backend as FastAPI Backend
    participant Web3 as Viem / Chain Client

    User->>Page: Navigate to /graph?evidence={evidenceHash}
    Page->>Loader: loadGraphData(evidenceHash)
    par Fetch Raw Evidence
        Loader->>Backend: GET /case-files/{evidenceHash}
        Backend-->>Loader: Raw JSON bytes
    and Fetch Derived Replay Outputs
        Loader->>Backend: GET /replay-outputs/{evidenceHash}
        Backend-->>Loader: Per-account JSONL stream
    and Fetch On-Chain Commitments
        Loader->>Web3: Read StressRegistry claims for evidenceHash
        Web3-->>Loader: Claim records
    end
    Loader->>Loader: Client-Side Audit: keccak256(rawBytes) == evidenceHash
    Loader->>Loader: Parse JSONL records into AccountOutcome objects
    Loader->>Loader: Consistency Audit: Sum per-account bad debt == caseFile.results.residualBadDebtUsd8
    Loader->>Page: Return validated GraphData model
    Page->>User: Render interactive SVG exposure graph (Nodes, Edges, Risk Badges)
```
