# StressProof — Security & Threat Model

This document outlines the security architecture, threat model, and explicit mitigations implemented in StressProof based on Section 20 of `implementationplan.md`.

---

## 1. Threat Matrix

| Threat ID | Vulnerability / Threat | Component | Mitigation Implemented |
|---|---|---|---|
| **S-01** | Reentrancy during bond withdrawal | `StressRegistry.sol` | Zero the caller's credit balance before making the external call (checks-effects-interactions). Pull payments only. |
| **S-02** | Wrong ETH bond amount sent | `StressRegistry.sol` | Strict equality check: `msg.value == BOND`. Over/underpayments revert with `WrongBond`. |
| **S-03** | Race conditions on deadlines | `StressRegistry.sol` | Strict comparison operators: `<` for actions allowed inside a window, `>=` for actions allowed after expiry. |
| **S-04** | Unauthorized or abusive dispute resolution | `StressRegistry.sol` | Only the designated `resolver` address can call `resolve()`. Can only act on `Challenged` claims before `resolutionDeadline`. Cannot resolve if resolver is attester or challenger. |
| **S-05** | Locked funds if resolver disappears | `StressRegistry.sol` | Anyone can call `expireUnresolved()` after `resolutionDeadline` elapses, refunding both attester and challenger bonds. |
| **S-06** | Server-Side Request Forgery (SSRF) via `caseFileURI` | `agents/common/fetch.py` | Restrict schemes to `https` and `ipfs`. Block private subnets (RFC 1918), link-local (`169.254.0.0/16`), and loopback (unless local dev flag is active). Disable HTTP redirects. |
| **S-07** | DoS via oversized or slow payload | `agents/common/fetch.py` | Stream body up to 25 MB max (`FETCH_MAX_BYTES`). Enforce 10s timeout (`FETCH_TIMEOUT_SEC`). If retrieval fails near deadline, challenge with `EVIDENCE_INVALID`. |
| **S-08** | Hash bypass via JSON re-serialization | `backend/`, `frontend/` | Never re-serialize JSON before hashing. Hash raw retrieved byte arrays directly. Reject non-canonical JSON during validation. |
| **S-09** | Path traversal via evidence hash parameters | `backend/storage/store.py` | Validate hash format strictly against `^0x[0-9a-f]{64}$` before interacting with the local filesystem. |
| **S-10** | Unauthorized writes to backend | `backend/` | Protect all `POST` routes with a bearer authentication token (`$API_WRITE_TOKEN`). |
| **S-11** | Cross-Site Scripting (XSS) via rationale or URIs | `frontend/` | Render agent rationale as plain text without HTML interpolation. Restrict external links to `https:` and `ipfs:`. |
| **S-12** | Private key exposure | Repository | `.env` gitignored, `.env.example` scrubbed of secrets. Separate keys for each of the 5 roles. |
| **S-13** | Dependency supply chain attacks | Python / Node | Pinned lockfiles (`uv.lock`, `frontend/package-lock.json`), Socket scan (`make socket-scan`, CI workflow `socket-scan.yml`; needs a Socket API token), npm holds back unapproved install scripts. See README, "Supply-chain scan". |
| **S-14** | Prompt injection or malformed LLM outputs | `agents/attester/` | LLM outputs are validated strictly by code (`shockBps` within `[-9000, -1]`). On validation failure, fall back to default fixed scenario. |
| **S-15** | Hash mismatch due to NIST SHA-3 vs. Keccak | `core/` | Use `eth-hash` / `eth-utils` exclusively. Pinned unit test verifying `keccak256("")`. |
| **S-16** | Client-Side Write Token Exposure | `frontend/` | **Mitigated:** Write operations (`POST /stress/run`) route through a server-side Next.js Route Handler (`frontend/src/app/api/stress/run/route.ts`). The private `API_WRITE_TOKEN` is maintained strictly server-side and never bundled into client JavaScript. Browser client requests require no write token. |

---

## 2. Disclosed MVP Limitations

The following limitations are inherent to the MVP architecture and must be explicitly communicated:

1. **Unverified Snapshot Completeness:** The watcher verifies that the calculation matches the committed snapshot, but does not verify whether borrowers were omitted from the snapshot or whether the snapshot reflects mainnet state.
2. **Fixed Bond Economics:** A fixed 0.01 ETH bond does not scale with the TVL or market impact of the vault.
3. **Challenge Front-Running:** A dishonest attester could theoretically front-run honest watchers with a sock-puppet challenge. (Commit-reveal or shared pools are planned post-MVP).
4. **Single-Pass Simplified Liquidation:** The model assumes 100% close factor without slippage or gas constraints.
