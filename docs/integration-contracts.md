# StressProof — Integration Contracts & API Specifications

This document defines the formal interfaces connecting the frontend, backend, smart contracts, and autonomous agents.

---

## 1. Smart Contract Interface (`IStressRegistry.sol`)

All addresses and values are accessed through `IStressRegistry`. Constants are immutable.

```solidity
interface IStressRegistry {
    enum State  { None, Pending, Challenged, Finalized, Rejected, Expired }
    enum Reason { NONE, WRONG_RESULT, EVIDENCE_INVALID }

    struct Claim {
        address attester;
        uint64  challengeDeadline;
        State   state;
        Reason  reason;
        address challenger;
        uint64  resolutionDeadline;
        bytes32 marketId;
        bytes32 evidenceHash;
        bytes32 replayReportHash;
        uint256 claimedResidualBadDebt;   // USD * 1e8
        uint256 counterResidualBadDebt;   // USD * 1e8, 0 for EVIDENCE_INVALID
        string  caseFileURI;
        string  replayReportURI;
    }

    event ClaimPosted(uint256 indexed claimId, address indexed attester, bytes32 indexed marketId,
                      uint256 claimedResidualBadDebt, bytes32 evidenceHash, string caseFileURI,
                      uint64 challengeDeadline);
    event ClaimChallenged(uint256 indexed claimId, address indexed challenger, Reason reason,
                          uint256 counterResidualBadDebt, string replayReportURI,
                          bytes32 replayReportHash, uint64 resolutionDeadline);
    event ClaimResolved(uint256 indexed claimId, bool challengeUpheld, address indexed winner,
                        uint256 amountCredited);
    event ClaimFinalized(uint256 indexed claimId);
    event ClaimExpired(uint256 indexed claimId);
    event Withdrawn(address indexed account, uint256 amount);

    function postClaim(bytes32 marketId, uint256 claimedResidualBadDebt, bytes32 evidenceHash,
                       string calldata caseFileURI) external payable returns (uint256 claimId);
    function challenge(uint256 claimId, Reason reason, uint256 counterResidualBadDebt,
                       string calldata replayReportURI, bytes32 replayReportHash) external payable;
    function resolve(uint256 claimId, bool challengeUpheld) external;
    function finalize(uint256 claimId) external;
    function expireUnresolved(uint256 claimId) external;
    function withdraw() external;

    function status(uint256 claimId) external view returns (State);
    function claim(uint256 claimId) external view returns (Claim memory);
    function credits(address account) external view returns (uint256);
    function claimCount() external view returns (uint256);

    function BOND() external view returns (uint256);
    function CHALLENGE_WINDOW() external view returns (uint64);
    function RESOLUTION_WINDOW() external view returns (uint64);
    function TOLERANCE_BPS() external view returns (uint16);
    function resolver() external view returns (address);
}
```

---

## 2. Vault Control Interface (`DemoVault.sol`)

```solidity
interface IDemoVault {
    function applyClaim(uint256 claimId) external;
    function resetControls() external;
    function borrowPaused() external view returns (bool);
    function maxLtvBps() external view returns (uint16);
    function lastAppliedClaimId() external view returns (uint256);
}
```

---

## 3. Backend REST API Endpoints

Source of truth: `backend/src/stressproof_backend/api/routes/*.py`. Deployed at `https://stressproof-hvf3.onrender.com`.

`POST` endpoints require `Authorization: Bearer $API_WRITE_TOKEN` (missing or malformed → `401`, wrong → `403`).
`GET` endpoints are public. CORS allows only `CORS_ORIGINS` (default `http://localhost:3000,http://127.0.0.1:3000`).
Browsers must not hold the write token: the frontend sends writes through its server route `/api/stress/run`.

### `GET /health`
`{"ok": true, "service": "stressproof-backend", "version": "0.1.0", "gitCommit": "<sha>", "datasets": ["weth-stable-fixture-v1"], "storage": "postgres"}`
(`storage` is `postgres` when `DATABASE_URL` is set, otherwise `filesystem`.)

### `GET /datasets` and `GET /datasets/{datasetId}/manifest`
`/datasets` returns `[{"datasetId", "dataClass", "forkBlock", "counts", "snapshotHash"}]`. The demo dataset is
`weth-stable-fixture-v1` (SYNTHETIC, see `docs/dataset-decision.md`). The manifest route returns the raw manifest
bytes; malformed id → `400`, unknown → `404`.

### `POST /stress/run`
Builds, self-validates and stores a case file for a dataset. Never touches the chain.
* **Request:**
  ```json
  {
    "datasetId": "weth-stable-fixture-v1",
    "scenario": { "asset": "WETH", "shockBps": -3000 },
    "agentRationale": "Optional plain-English description"
  }
  ```
  `shockBps` must be an integer in `[-9000, -1]`; `asset` must be `"WETH"`; no extra keys (otherwise `422`).
  Unknown dataset → `404`. Default rationale: `"Phase 1 fixed scenario: <shockBps> bps WETH shock."`
* **Response (200 OK):**
  ```json
  {
    "evidenceHash": "0x...",
    "caseFileURI": "https://stressproof-hvf3.onrender.com/case-files/0x...",
    "caseFileHttpURL": "https://stressproof-hvf3.onrender.com/case-files/0x...",
    "results": {
      "liquidatableAccounts": 4,
      "debtAtRiskUsd8": "3374300000002",
      "liquidationVolumeUsd8": "3174300000001",
      "residualBadDebtUsd8": "200000000001"
    },
    "dataClass": "SYNTHETIC",
    "sizeBytes": 2288
  }
  ```
  Amounts are decimal strings (use `BigInt`); `liquidatableAccounts` is a number. URIs use `BACKEND_PUBLIC_URL`.
  Each call also appends a `CLAIM_BUILT` feed entry.

### `GET /case-files/{evidenceHash}`
Returns the exact stored bytes (hash the raw body, never re-serialized JSON) with headers:
* `Content-Type: application/json`
* `Cache-Control: public, max-age=31536000, immutable`
* `X-Content-Keccak256: 0x...`

Malformed hash (not `0x` + 64 lowercase hex) → `400`; unknown → `404`.

### `POST /case-files`
Raw canonical case-file bytes. Must pass `validate()` (V-01..V-13), otherwise `422` with
`{"detail": {"violations": ["V-03", ...], "messages": [...]}}`. Body over `MAX_BODY_BYTES` → `413`.
* **201 Created** for a new file, **200 OK** with the same body if that hash is already stored:
  `{"evidenceHash": "0x...", "caseFileURI": "https://.../case-files/0x..."}`

### `POST /replay-reports` and `GET /replay-reports/{hash}`
`POST` takes the raw canonical bytes of a report with exactly the keys in `docs/schemas/replay-report.md`
(otherwise `422`); **201** new, **200** already stored: `{"reportHash": "0x...", "reportURI": "https://..."}`.
`GET` returns the exact stored bytes with the same headers as case files; `400` / `404` as above.

### `GET /replay-outputs/{evidenceHash}` (WP-6, read-only)
Returns the per-account outcomes that `POST /stress/run` stored for that case file (plan §8.5): one canonical
JSON line per account, `{"collateralValueUsd8","id","liquidatable","repaidUsd8","residualUsd8"}`, as
`application/x-ndjson` with `X-Evidence-Hash` and an immutable cache header. These bytes are derived data and
do **not** hash to the evidenceHash, so there is no `X-Content-Keccak256`. `400` malformed hash, `404` when no
outputs are stored (for example a case file uploaded with `POST /case-files`). There is no write route.

### `POST /feed` and `GET /feed`
Append-only log of agent-reported actions (chain events stay authoritative).
* **POST request:** `{"actor": "watcher", "kind": "REPLAY_MATCH", "claimId": "1", "txHash": null, "data": {...}}`
  * `actor`: `attester`, `malicious_attester`, `malicious`, `watcher`, `resolver`, `backend`, `ui`, `user`
  * `kind`: one of the 20 kinds in implementationplan.md §8.6
  * `claimId`: decimal string or null; `data`: finite JSON object, at most 16 KB
* **POST response (201):** `{"seq": 42}`
* **GET:** `/feed?since=<seq>&limit=<1..200, default 50>` →
  `{"entries": [{"seq", "ts", "actor", "kind", "claimId", "txHash", "data"}], "nextSince": <last seq>}`.
  Poll with `since=nextSince`; `seq` is unique, increasing and never skipped, also across restarts.

### `GET /graph/exposure`
Phase 2. Returns `503` with `{"label": "estimated exposure", "nodes": [], "links": []}` until the graph exists.

### Not used in the MVP
IPFS pinning (§16.2) is not implemented: `IPFS_*` variables are unused and `caseFileURI` is always the backend
URL. Readers verify the keccak256 hash, so the transport does not need to be trusted.
