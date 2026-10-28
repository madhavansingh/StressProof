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

All `POST` endpoints require authorization header: `Authorization: Bearer $API_WRITE_TOKEN`. `GET` endpoints are public.

### `POST /stress/run`
Executes scenario on a dataset snapshot, builds and stores the case file.
* **Request:**
  ```json
  {
    "datasetId": "weth-stable-19000000-v1",
    "scenario": { "asset": "WETH", "shockBps": -3000 },
    "agentRationale": "Optional plain-English description"
  }
  ```
* **Response (200 OK):**
  ```json
  {
    "evidenceHash": "0x...",
    "caseFileURI": "http://127.0.0.1:8000/case-files/0x...",
    "results": {
      "liquidatableAccounts": 4,
      "debtAtRiskUsd8": "3374300000002",
      "liquidationVolumeUsd8": "3174300000001",
      "residualBadDebtUsd8": "200000000001"
    },
    "dataClass": "REAL",
    "sizeBytes": 14205
  }
  ```

### `GET /case-files/{evidenceHash}`
Returns exact, raw stored bytes with headers:
* `Content-Type: application/json`
* `Cache-Control: public, max-age=31536000, immutable`
* `X-Content-Keccak256: 0x...`

### `POST /replay-reports`
Stores a watcher's generated verification report.
* **Request:** Raw canonical bytes of the report.
* **Response (201 Created):** `{"reportHash": "0x...", "reportURI": "http://..."}`

### `GET /replay-reports/{hash}`
Returns exact raw bytes of the replay report.

### `POST /feed` & `GET /feed`
Append-only log of agent actions and chain events.
* Entry format: `{"seq": 42, "ts": "2026-10-28T...", "actor": "watcher", "kind": "REPLAY_MATCH", "claimId": "1", "data": {...}}`
