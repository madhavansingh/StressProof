# StressProof: Security Model & Threat Analysis

This document provides a comprehensive security assessment, threat model, mitigation catalog, and residual risk analysis for the StressProof verification protocol.

---

## 1. Threat Modeling Methodology

StressProof models threats across five distinct architectural surfaces:
1. **Smart Contracts (`contracts/`):** Financial escrow, state transitions, reentrancy, access control, and temporal windows.
2. **Deterministic Replay Engine (`core/`):** Parsing edge-cases, numerical overflow/underflow, canonical serialization, and hash collision resistance.
3. **Autonomous Agent Runtime (`agents/`):** SSRF, hostile payload ingestion, denial of service, memory exhaustion, and transaction replay.
4. **Backend REST API (`backend/`):** Authentication bypass, path traversal, injection, and resource exhaustion.
5. **Client-Side Web Application (`frontend/`):** Cross-site scripting (XSS), wallet manipulation, token leakage, and dependency supply-chain integrity.

---

## 2. Threat Matrix (S-01 through S-16)

The following table details the 16 primary threat vectors modeled during protocol design and the implemented mitigations:

| ID | Attack Vector | Target Surface | Mechanism / Mitigation Implemented | Verification / Test Reference |
|---|---|---|---|---|
| **S-01** | Reentrancy during bond withdrawal | `StressRegistry.sol` | Zero the caller's credit balance before making the external call (checks-effects-interactions). Pull payments only. | `contracts/test/StressRegistryResolution.t.sol::test_withdraw_reentrantCallRevertsWholeWithdrawal` |
| **S-02** | Wrong ETH bond amount posted | `StressRegistry.sol` | Strict equality check: `msg.value == BOND`. Over/underpayments revert with custom error `WrongBond`. | `contracts/test/StressRegistry.t.sol::testFuzz_postClaim_wrongBond` |
| **S-03** | Race conditions on deadlines | `StressRegistry.sol` | Strict comparison operators: `<` for actions allowed inside a window, `>=` for actions allowed after expiry. | `contracts/test/StressRegistry.t.sol::test_challenge_atDeadline` |
| **S-04** | Unauthorized or abusive dispute resolution | `StressRegistry.sol` | Only the designated `resolver` address can call `resolve()`. Can only act on `Challenged` claims before `resolutionDeadline`. Cannot resolve if resolver is attester or challenger. | `contracts/test/StressRegistryResolution.t.sol::test_resolve_notResolver` |
| **S-05** | Permanent capital lock if resolver disappears | `StressRegistry.sol` | Anyone can call `expireUnresolved()` after `resolutionDeadline` elapses, refunding both attester and challenger bonds. | `contracts/test/StressRegistryResolution.t.sol::test_expire_atDeadline` |
| **S-06** | Server-Side Request Forgery (SSRF) via `caseFileURI` | `agents/common/fetch.py` | Restrict schemes to `https` and `ipfs`. Block private subnets (RFC 1918), link-local (`169.254.0.0/16`), and loopback (unless local dev flag is active). Disable HTTP redirects. | `agents/tests/test_fetch.py::test_ssrf_blocking` |
| **S-07** | DoS via oversized or slow payload | `agents/common/fetch.py` | Stream body up to 25 MB max (`FETCH_MAX_BYTES`). Enforce 10s timeout (`FETCH_TIMEOUT_SEC`). If retrieval fails near deadline, challenge with `EVIDENCE_INVALID`. | `agents/tests/test_fetch.py::test_max_bytes_limit` |
| **S-08** | Hash bypass via JSON re-serialization | `backend/`, `frontend/` | Never re-serialize JSON before hashing. Hash raw retrieved byte arrays directly. Reject non-canonical JSON during validation. | `core/tests/test_canonical.py`, `frontend/tests/verify.test.ts` |
| **S-09** | Path traversal via evidence hash parameters | `backend/storage/store.py` | Validate hash format strictly against `^0x[0-9a-f]{64}$` before interacting with the local filesystem. | `backend/tests/test_api.py::test_path_traversal_rejected` |
| **S-10** | Unauthorized writes to backend | `backend/` | Protect all `POST` routes with a bearer authentication token (`$API_WRITE_TOKEN`). | `backend/tests/test_api.py::test_write_requires_auth` |
| **S-11** | Cross-Site Scripting (XSS) via rationale or URIs | `frontend/` | Render agent rationale as plain text without HTML interpolation. Restrict external links to `https:` and `ipfs:`. | `frontend/tests/xss.test.ts` |
| **S-12** | Private key exposure | Repository | `.env` gitignored, `.env.example` scrubbed of secrets. Separate keys for each of the 5 roles. | `scripts/tests/test_write_deployment.py` |
| **S-13** | Dependency supply chain attacks | Python / Node | Pinned lockfiles (`uv.lock`, `frontend/package-lock.json`), Socket scan (`make socket-scan`, CI workflow `socket-scan.yml`). Mitigate known CVEs. | `scripts/tests/test_socket_scan_sh.py`, README |
| **S-14** | Prompt injection or malformed LLM outputs | `agents/attester/` | LLM outputs are validated strictly by code (`shockBps` within `[-9000, -1]`). On validation failure, fall back to default fixed scenario. | `core/tests/test_validation.py` |
| **S-15** | Hash mismatch due to NIST SHA-3 vs. Keccak | `core/` | Use `eth-hash` / `eth-utils` exclusively. Pinned unit test verifying `keccak256("")`. | `core/tests/test_hashing.py::test_keccak_empty_bytes` |
| **S-16** | Client-Side Write Token Exposure | `frontend/` | Write operations (`POST /stress/run`) route through a server-side Next.js Route Handler (`frontend/src/app/api/stress/run/route.ts`). The private `API_WRITE_TOKEN` is maintained strictly server-side and never bundled into client JavaScript. Browser client requests require no write token. | `frontend/tests/postClaimRequest.test.ts` |

---

## 3. Smart Contract Security Architecture

### 3.1. Reentrancy Immunity via Pull Payments
StressProof smart contracts strictly follow the **Checks-Effects-Interactions** pattern. In `StressRegistry.sol`:
```solidity
function withdraw() external override {
    uint256 amt = credits[msg.sender];
    if (amt == 0) revert NothingToWithdraw();

    credits[msg.sender] = 0;
    totalCredited -= amt;
    emit Withdrawn(msg.sender, amt);

    (bool ok, ) = msg.sender.call{value: amt}("");
    if (!ok) revert TransferFailed();
}
```
Because `credits[msg.sender]` is set to `0` prior to the external `.call`, reentrant attempts to re-enter `withdraw()` immediately revert with `NothingToWithdraw()`. This was formally verified under invariant testing (25,600 fuzz calls) and in `StressRegistryResolutionTest::test_withdraw_reentrantCallRevertsWholeWithdrawal`.

### 3.2. Accounting Invariants
The registry guarantees that total protocol assets always cover total protocol liabilities:
$$\text{address}(\text{this}).\text{balance} \ge \text{totalLocked} + \text{totalCredited}$$
- `totalLocked` tracks funds currently escrowed in open `Pending` or `Challenged` claims.
- `totalCredited` tracks unsettled winning credits available for withdrawal.
- Any forced ether injection (via `selfdestruct` or mining coinbase rewards) does not affect accounting or claim settlement math.

---

## 4. SSRF Defense Specification (`agents/common/fetch.py`)

When the Watcher agent evaluates an on-chain claim, it fetches the case file from an untrusted `caseFileURI`. An attacker could attempt to pass internal infrastructure URLs (e.g. `http://169.254.169.254/latest/meta-data/` or internal database endpoints).

To eliminate Server-Side Request Forgery, `EvidenceFetcher` enforces:
1. **Scheme Whitelist:** Only `https://` and `ipfs://` are permitted. Plain `http://` is strictly prohibited unless `FETCH_ALLOW_LOCALHOST=true` is set for local Anvil testing.
2. **IP Denylist Resolution:** Prior to opening a TCP connection, the hostname is resolved to IP addresses:
   - Blocks IPv4 Private Subnets (RFC 1918): `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.
   - Blocks Link-Local & Cloud Metadata: `169.254.0.0/16` (AWS, GCP, Azure metadata services).
   - Blocks IPv6 Loopback: `::1/128`, `fe80::/10`.
   - Blocks Multicast & Broadcast: `224.0.0.0/4`, `255.255.255.255/32`.
3. **Redirect Prohibition:** HTTP redirects (301, 302, 307) are disabled (`follow_redirects=False`) to prevent redirect-based filter evasion.
4. **Streaming Resource Limit:** Responses are streamed in chunks up to $25\text{ MB}$ (`FETCH_MAX_BYTES`). Requests exceeding $25\text{ MB}$ are aborted immediately, preventing memory exhaustion attacks.

---

## 5. Supply-Chain Security & Dependency Auditing

### 5.1. Socket Security Integration
Supply chain scanning is integrated into the CI/CD pipeline via `scripts/socket_scan.sh` and `.github/workflows/socket-scan.yml`. It evaluates packages against typosquatting, hidden install scripts, network telemetry, and critical CVEs.

### 5.2. Audit Findings & Remediations
1. **Vitest 1.6.1 Upgrade:**
   - Previous versions pulled `tinypool 0.8.4` which carried critical CVEs (GHSA-5gmw-xhrv-c9v3).
   - **Remediation:** Upgraded to `vitest 4.1.12` and `vite 8.3.5`. Dev-only vulnerabilities reduced to zero.
2. **Next.js 14.2.35 Advisories (CVE-2024-34351, CVE-2024-46982):**
   - The Image Optimization API in Next.js 14 carries RCE and cache poisoning advisories.
   - **Remediation:** Disabled Next.js Image Optimization in `frontend/next.config.mjs` via `images.unoptimized: true`. Verified that calls to `/_next/image` return 404 before processing parameters.
   - **Long-Term Plan:** Migration to Next.js 15.5.28+ is scheduled post-submission.
3. **Python Workspace Audit:**
   - `uv audit` reports zero known vulnerabilities across 69 installed Python packages.

---

## 6. Disclosed Protocol Limitations & Residual Risks

1. **Unverified Historical Snapshot Completeness:**
   - The protocol cryptographically guarantees that the replayed calculation exactly matches the committed snapshot.
   - It does *not* prove on-chain that the snapshot represents all real Aave v3 borrowers at block $N$. (Doing so trustlessly requires zero-knowledge storage proofs over Ethereum archive state).
2. **Fixed Bond Capital Efficiency:**
   - The $0.01\text{ ETH}$ bond is uniform regardless of market size. A $\$50\text{M}$ vault risk claim carries the same bond as a $\$100\text{k}$ vault claim.
   - Production iterations will introduce dynamic bonds scaled to total market value at risk.
3. **Challenge Front-Running:**
   - In a public mempool, an adversary could observe an honest watcher's challenge transaction and attempt to front-run it with an identical challenge to steal the slashing reward.
   - Future protocol iterations will implement commit-reveal challenge submissions.
4. **Designated Resolver Trust:**
   - The MVP uses a single designated resolver address to break ties during disputes. If this key is lost, disputes expire safely via `expireUnresolved()`. In production, this role transitions to an interactive zk-fraud-proof system or decentralized oracle council.
