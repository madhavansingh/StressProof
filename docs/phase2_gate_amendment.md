# StressProof — Amendment: Conditional Phase 2 Start While GATE-24 Is Pending

| | |
|---|---|
| **Status** | **APPROVED by the sole project owner on 2026-10-30 (§9)** |
| `GATE-24` | **PENDING TESTNET ACCEPTANCE** |
| `PHASE 2` | **CONDITIONAL START APPROVED** |
| `FINAL RELEASE` | **BLOCKED UNTIL GATE-24 PASSES** |
| Date drafted | 2026-10-30 |
| Amends | `docs/implementationplan.md` §21.5, §24 (H24 row), §25, §26 (H24 row); `docs/team-ownership.md` §2 (Hour 24 note) |
| Repository state when drafted | branch `blockchain`, commit `0d354a2` |
| Governance | Single project owner (see `CONTRIBUTING.md`, Governance) |

This document changes the **order** in which work may start. It does not change, weaken or replace
any GATE-24 requirement, and it does not record GATE-24 as passed. The original text stays in the
implementation plan unchanged; the plan only gains notes pointing here.

---

## 1. Original GATE-24 requirements (verbatim)

From `docs/implementationplan.md` §21.5:

> **[GATE] GATE-24:** `e2e_local.sh` passes **and** steps 3 to 7 pass once on the testnet with real windows (no time warp).

Steps 3 to 7 of the §21.5 E2E script:

> 3. Honest attester posts. Assert the watcher logs `REPLAY_MATCH` and sends no challenge transaction.
> 4. `cast rpc evm_increaseTime 121` then `evm_mine`. Run `finalize` and `applyClaim`. Assert `maxLtvBps == 5000`. `borrow(10000e8, 7000e8)` reverts with `LtvTooHigh`.
> 5. Malicious attester posts 3R. Assert the watcher challenges within 10 s with `WRONG_RESULT` and counter = R.
> 6. Resolver: `resolve <id> --yes`. The state is Rejected. The watcher withdraws. Its balance delta is `+BOND − gas`.
> 7. `applyClaim(maliciousId)` reverts with `NotFinalized`.

(On the testnet, step 4's time warp is replaced by waiting out the real 120 s challenge window.)

From §24, H24 row:

> **GATE-24** (§21.5): all three people watch the full flow on testnet. If it fails, **everyone fixes Phase 1. No Phase 2 work starts**

Phase 1 acceptance criteria (§24), each a checkbox on the H24 call:

> 1. An honest claim is posted on the testnet with `caseFileURI` and `evidenceHash` visible in the UI.
> 2. The watcher feed shows `HASH_OK` and `REPLAY_MATCH`. No challenge transaction is sent.
> 3. After 120 s, `finalize` succeeds. `applyClaim` sets max LTV to 50%. Try borrow at 70% reverts in the UI.
> 4. A malicious claim (3R) is challenged within 15 s of `ClaimPosted` with counter = R.
> 5. The resolver CLI shows the same R and upholds the challenge. The watcher's withdraw delta is `+BOND` (excluding gas).
> 6. `applyClaim(maliciousId)` reverts with `NotFinalized` in the UI.
> 7. In-browser hash verification shows green for both case files.
> 8. `forge test` and `pytest` are all green.

The same rule appears in §25 ("These are allowed after `GATE-24`"), §26 (H24: "Gate fails → Pause all
Phase 2 work until it passes") and `docs/team-ownership.md` §2 ("No Phase 2 work starts until GATE-24 passes!").

**None of this text is removed or reworded by this amendment.**

---

## 2. Why the team proposes a sequencing change

Evidence as of 2026-10-30 (each item was checked, not assumed):

| Requirement | Status | Evidence |
|---|---|---|
| `e2e_local.sh` (local Anvil, steps 1–10) | Passed earlier | 101/101 checks, run by the team at commit `49a3c98`; only frontend files and one `.env.example` comment changed outside `frontend/` up to `0d354a2`. Not re-run since. |
| Unit suites | Passing | Forge 95/95, pytest 725 passed / 57 skipped (56 Postgres-backed backend tests need a disposable `TEST_DATABASE_URL`), vitest 148/148 at `0d354a2`. |
| Testnet deployment | **Not done** | `deployments/84532.json` still holds zero-address placeholders. No Base Sepolia broadcast record exists. |
| Testnet preflight | Passing | `make testnet-preflight` passes with dedicated role keys (public Anvil/Hardhat keys are refused by `Deploy.s.sol` and the preflight). |
| Role funding | **Incomplete** | Deployer and resolver meet their minimums; the honest attester, watcher and malicious attester each hold 0.002 ETH of the 0.011 ETH needed (0.01 ETH bond + gas). |
| Testnet steps 3–7 with real windows | **Not run** | Blocked on deployment, which is blocked on funding. |
| H24 observation (now by the project owner) | **Not done** | Depends on the testnet run. |

The remaining gate work is operational (obtain 0.027 ETH of Base Sepolia test ETH, deploy, run steps
3–7 with real windows, observed by the project owner). It does not need new Phase 1 code. Several Phase 2 deliverables do not
depend on testnet contracts at all (§3). Holding all of them until a faucet issue is solved idles two of
three developers. The proposal lets that independent work start, under the controls below, while
GATE-24 remains the team's first priority.

---

## 3. Proposed conditional Phase 2 entry policy

Approved (§9):

1. **Phase 2 implementation may begin conditionally while GATE-24 remains pending.**
2. **GATE-24 remains a mandatory acceptance milestone.** Its requirements in §1 are unchanged.
3. **GATE-24 is never marked PASS without the testnet evidence listed in §8.** No document, README, demo
   script, commit message or pitch may say or imply that testnet acceptance is complete before then.
4. **GATE-24 work pre-empts Phase 2 work.** As soon as funding is available, the deployment and the
   steps 3–7 run take priority over any Phase 2 task, and the owner-observed run is scheduled first.
5. **Only items classified ALLOWED or CONDITIONAL in §4 may start.** CONDITIONAL items must first record
   their assumptions and keep the interfaces in §5 isolated. BLOCKED items wait for the evidence in §7.
6. **Each new task re-checks its dependencies** against §4 before starting; if it touches a BLOCKED
   dependency it stops.
7. **No production launch, mainnet deployment, or public claim of completed testnet acceptance** before
   GATE-24 passes. The final release stays blocked until then.
8. **The 120 s challenge window and 300 s resolution window are not changed** to speed anything up.
9. **The H24 observation remains part of the GATE-24 acceptance record** (§8). Under single-owner
   governance it is the project owner's observation (owner decision, 2026-10-30).
10. **If the testnet run fails,** §26's rule applies again: Phase 2 work pauses and everyone fixes Phase 1.

---

## 4. Phase 2 dependency matrix

Source of the items: §24 Phase 2 table (H24–H34), the Phase 2 done criteria ("the graph is reconciled
with the snapshot, the LLM proposal path produces a valid claim end to end, and the Socket report is in
the README"), §17 (TigerGraph), §18 (AI layer), §25 (scope and stretch items) and §24 Phase 3.

**Ownership.** The plan names Person A (contracts), Person B (data, core, backend, agents, TigerGraph,
LLM) and Person C (frontend). The team documents name developers, and they settle most of the mapping:

- `CONTRIBUTING.md`: Developer 3 (Blockchain & AI) owns `contracts/`, `agents/` and "Phase 2 TigerGraph & LLM".
- `docs/developer-setup.md`, `README.md`, `docs/team-ownership.md`: Developer 1 owns `frontend/`;
  Developer 2 owns `core/`, `pipeline/` and `backend/`.

So Person A maps to Developer 3, Person C to Developer 1, and Person B's work splits by directory
(core, pipeline, backend: Developer 2; agents: Developer 3). TigerGraph and LLM features belong to
Developer 3. **Open question:** the §17 loader and reconciler files the plan places under `pipeline/`
are in Developer 2's directory; Developer 2 must confirm who owns them (§9). The owner column below
follows these documents and now records the **original area lead** only: under single-owner governance
the project owner is responsible for, and may work on, every item. The `pipeline/` file-area question is
therefore closed: the owner decides where the TigerGraph loader and reconciler live.

| # | Deliverable (plan reference) | Class | Reason | Dependencies | Risks | Owner |
|---|---|---|---|---|---|---|
| 1 | Socket scan of both lockfiles; fix or pin flagged packages; write-up in README (§24 H24–26, S-13, "never cut") | **ALLOWED** | Static analysis of `uv.lock` and the frontend lockfile; no chain or testnet need | Lockfiles; Socket tool access **[UNVERIFIED usage in plan]** | Pinning a flagged package could change behaviour: re-run all suites and local E2E after any lockfile change | Developer 3 (plan: A) |
| 2 | TigerGraph workspace and `schema.gsql` applied (§17.1, §24 H24–26) | **CONDITIONAL** | Uses the committed snapshot, not testnet state | A TigerGraph account and credentials (none exist yet); dataset choice (only the 6-account synthetic fixture exists) | Credentials in git; a trivial graph from 6 synthetic accounts; schema drift from §17.1 | Developer 3 (D3-7) |
| 3 | `tg_load.py` and `tg_reconcile.py`, which **must fail loudly on mismatch** (§17.2–17.3, §24 H26–29) | **CONDITIONAL** | Loads and reconciles the snapshot; no chain dependency | Item 2; the snapshot and `replay_outputs`; agreement on who owns the files under `pipeline/` | A silent reconcile would mislabel data (S-16); never in the verdict path | Developer 3 with Developer 2 (file area) |
| 4 | Graph queries, Appendix C (§17.4, §24 H32–34) | **CONDITIONAL** | Read-only analytics over the graph | Items 2–3; GSQL syntax is **[UNVERIFIED]** in the plan | Query results must never feed a verdict | Developer 3 |
| 5 | `/graph/exposure` backend route (currently a 503 stub) and frontend integration, colours, real/synthetic filter (§24 H26–29) | **CONDITIONAL** | API and UI over local data | Items 2–3 for live data; may use `replay_outputs` until then | Showing synthetic data without its label (S-16) | Developer 2 (route), Developer 1 (UI) |
| 6 | Graph page skeleton with a static graph from `replay_outputs` (§24 H24–26) | **ALLOWED** | Reads local replay outputs; no chain or TigerGraph need | `replay_outputs` files | Must carry the data-class banner | Developer 1 |
| 7 | LLM scenario proposer with strict validation, retry-once and fixed-scenario fallback (§18.2, §24 H32–34) | **CONDITIONAL** | Can be built and unit-tested with a mocked model and run on local Anvil; output is validated in code and committed through `evidenceHash` | An LLM API key (none exists); SDK not in `uv.lock` (needs a team decision to add); item 4 for graph context | Prompt injection, invalid output, a key in git, any path from AI to a verdict (S-14, §18.1) | Developer 3 (D3-7) |
| 8 | LLM path "produces a valid claim end to end" on the testnet (Phase 2 done criterion) | **BLOCKED** | Needs deployed testnet contracts and a passing flow | GATE-24 evidence (§7) | Claiming Phase 2 done without it | Developer 3 |
| 9 | Rationale shown in claim detail (as text) and feed line "LLM proposed −X bps" (§24 H32–34, §18.2 item 5) | **CONDITIONAL** | UI work against the case-file and feed schemas; can use fixtures | Item 7's output shape; schema changes need a `SCHEMA:` commit | XSS: render as plain text only (S-11, T-F-05) | Developer 1 |
| 10 | Agent feed polish (§25) | **ALLOWED** | Backend and frontend work on the existing feed | Existing feed schema (C-04) | Changing the feed schema without notice | Developer 2 (backend), Developer 1 (UI) |
| 11 | Assumptions panel text final, banners, empty and error states (§24 H29–32) | **ALLOWED** | Frontend copy and states | §10.4 assumptions text (word for word) | Wording that implies testnet acceptance (forbidden by §3.3) | Developer 1 |
| 12 | Security pass on §20 and re-run of the E2E (§24 H29–32) | **ALLOWED (local)** | Review plus local `e2e_local.sh` on Anvil; no testnet writes | Current code | The testnet part of any re-run is BLOCKED | Developer 3 |
| 13 | Help with the transaction UX: wallet-signed publish, challenge, finalize, apply in the browser (§24 H29–32) | **ALLOWED (local)** | Can be exercised with MetaMask on local Anvil | Local stack | No wallet-signed browser flow has been completed yet, even locally | Developer 3 with Developer 1 |
| 14 | Demo dry run and timing (§24 H32–34) and full rehearsal plus backup video on the testnet (§24 Phase 3) | **BLOCKED** | Defined as testnet activities | Testnet deployment and GATE-24 | Rehearsing against local data and presenting it as testnet | Everyone |
| 15 | Stretch: Flow voice input, Dodo Payments checkout narrative (§25) | **CONDITIONAL** | Isolated from the verdict path; lowest priority and first to cut (§26) | Each sponsor's bounty text read first (**[UNVERIFIED]** APIs) | Scope creep away from the gate | Developer 1 (UI) unless reassigned |
| 16 | Stretch: Cake Wallet (§25) | **CONDITIONAL / writes BLOCKED** | Connection and browse-only display already work; Cake Wallet cannot sign on chain 31337 or 84532 | A deployment on a chain Cake Wallet supports, which is not in scope | Presenting browse-only as a working signer | Developer 1, Developer 3 |

Not Phase 2 but still open from Phase 1, and therefore part of GATE-24 or its prerequisites: the testnet
deployment with real thresholds (§24 H12–20) and the REAL vs SYNTHETIC dataset decision (§24 H5–8; the
only dataset today is the 6-account synthetic fixture).

**Can start immediately once approved:** items 1, 6, 10, 11, 12, 13.
**Can start after recording assumptions:** items 2, 3, 4, 5, 7, 9, 15, 16 (read-only parts).
**Blocked:** items 8, 14, and Cake Wallet writes.

---

## 5. Security and testing restrictions

This amendment does **not** authorize:

- a testnet deployment or any testnet transaction;
- contract changes that bypass or weaken existing controls (bond, state machine, windows, resolver limits, pull payments);
- production changes (Render, Neon or any hosted service);
- a mainnet deployment;
- funding or transferring ETH;
- changing the 120 s challenge or 300 s resolution windows;
- removing deterministic verification, hash verification before replay, or watcher and resolver safeguards.

While GATE-24 is pending, Phase 2 work must also follow these rules:

1. **Verdict path isolation (§3.1, §18.1).** TigerGraph and LLM code is never imported by
   `stressproof_core`'s replay or validation, the watcher's verdict logic, or the resolver. The AI only
   proposes `shockBps` and writes a rationale; it never decides verdicts, signs, or holds keys.
2. **Frozen interfaces.** No change to `contracts/src/IStressRegistry.sol`, the ABIs, the case-file
   schema or `deployments/*.json` without the existing `ABI:` / `SCHEMA:` process. Any such change
   invalidates the local E2E result, which must then be re-run before the testnet run.
3. **Generated deployments only.** `deployments/84532.json` is written only by `scripts/deploy.sh` from
   confirmed receipts. No placeholder or hand-entered address may be used by Phase 2 code as if real.
4. **Local writes only.** Phase 2 testing uses local Anvil or mocks. No agent, script or test may send
   a testnet transaction until GATE-24 work authorizes it.
5. **Secrets.** TigerGraph and LLM credentials live only in git-ignored env files. Prompts carry no
   addresses (§18.2 item 1). Keys never appear in logs, prompts or the UI.
6. **Data labelling (S-16).** Every graph view and LLM rationale built on the synthetic fixture shows
   the SYNTHETIC label.
7. **Tests.** New Phase 2 code ships with unit tests (mocked TigerGraph and LLM; §21.3's T-P-60 for LLM
   output). Before merging anything that touches agents, core, contracts or the backend, run `forge
   test`, `pytest` and the frontend tests, and re-run `e2e_local.sh`.
8. **No public claims.** No README, demo or pitch text may state that testnet acceptance, GATE-24 or
   Phase 2 is complete before the evidence exists.

---

## 6. Risks introduced by parallel development, and mitigations

| Risk | Mitigation |
|---|---|
| GATE-24 slips further because attention moves to Phase 2 | §3.4: GATE-24 work pre-empts Phase 2. The project owner obtains the remaining 0.027 ETH and schedules the owner-observed testnet run as soon as it arrives. |
| The testnet run exposes a Phase 1 bug, and Phase 2 work built on top must be redone | Phase 2 stays off the verdict path and off the contract interfaces (§5.1–5.2). If the run fails, §3.10 pauses Phase 2. |
| Interface or schema drift breaks the gate run | Frozen ABI and schemas, the `ABI:`/`SCHEMA:` process, and a local E2E re-run before the testnet run. |
| Phase 2 code accidentally reaches the verdict path | Import isolation (§5.1), with a reviewer check on every Phase 2 change to agents or core. |
| Premature or misleading claims of acceptance | §3.3 and §5.8; the statuses at the top of this document stay until §8 is met. |
| Credentials leak (TigerGraph, LLM, testnet keys) | Git-ignored env files only; the existing `.env.*` ignore rule; the pre-push secret check (S-12). |
| A trivial graph or meaningless AI output from a 6-account synthetic dataset | Label as SYNTHETIC; treat the REAL vs SYNTHETIC decision as an open Phase 1 item before any analytics claim. |
| Dependency risk from new SDKs (TigerGraph, LLM) | The team agrees before adding them to the lockfiles, and the Socket scan (item 1) covers them. |
| Same-machine case files limit testnet evidence | Already accepted for the gate run: evidence URLs point at `127.0.0.1` and only local agents can fetch them. Revisit before any public demo. |

---

## 7. Evidence required before BLOCKED work may proceed

BLOCKED items (8, 14, Cake Wallet writes) may start only when **all** of the following exist in the
repository or the acceptance record:

1. `deployments/84532.json` written by `scripts/deploy.sh` from confirmed receipts, committed, with the
   on-chain bytecode of the registry, vault and market confirmed on Base Sepolia (chain 84532).
2. Read-only confirmation that the deployed parameters match the plan: bond 0.01 ETH, windows 120 s and
   300 s, pause threshold 400000000002 and LTV threshold 100000000000 (USD8), reduced and default max
   LTV 5000 and 8000 bps, tolerance 0, and the five distinct role addresses.
3. GATE-24 passed as defined in §8.

---

## 8. Criteria for final GATE-24 completion

GATE-24 passes only when all of the following are recorded:

1. `e2e_local.sh` passes on the commit that was deployed (or a later re-run after any change to
   contracts, agents, core or backend).
2. Steps 3 to 7 of §21.5 pass once on Base Sepolia with real windows (no time warp), with:
   - transaction hashes and block numbers for the honest post, finalize, apply, malicious post,
     challenge, resolve and withdraw;
   - the watcher log or feed lines showing `HASH_OK`, `REPLAY_MATCH` for the honest claim and
     `WRONG_RESULT` with counter = R for the malicious claim, with the challenge inside the window;
   - read-only proof that `maxLtvBps == 5000` after apply, that a 70% borrow reverts `LtvTooHigh`, and
     that `applyClaim(maliciousId)` reverts `NotFinalized`;
   - the watcher's balance delta of `+BOND` excluding gas.
3. Phase 1 acceptance criteria 1–8 (§1) each checked on the H24 call.
4. **The project owner observed the full testnet run**, recorded below with name and date.
   *Owner decision (2026-10-30):* the original criterion ("all three team members observed the run",
   implementation plan §24 H24 row) predates the single-owner governance. The sole project owner
   replaced it with observation by the project owner. Every other GATE-24 criterion is unchanged.

Only then do the statuses change to `GATE-24: PASSED` and the BLOCKED items in §4 open.

| Observer | Name | Date | Confirmed full run observed |
|---|---|---|---|
| Project owner | | | ☐ |

---

## 9. Approval

**Approved by the sole project owner on 2026-10-30.**

StressProof moved to single-owner governance on 2026-10-30: one project owner holds decision authority
and overall accountability (`CONTRIBUTING.md`, Governance). The owner's written instruction of that date
approves this conditional Phase 2 sequencing amendment and sets:

- `GATE-24: PENDING TESTNET ACCEPTANCE`
- `PHASE 2: CONDITIONAL START APPROVED`
- `FINAL RELEASE: BLOCKED UNTIL GATE-24 PASSES`

The earlier requirement that Developer 1, Developer 2 and Developer 3 each approve this amendment is
superseded by that governance change. No individual developer approvals were collected or are recorded
here.

| Approver | Role | Decision | Date |
|---|---|---|---|
| Project owner | Sole project owner (decision authority) | Approve | 2026-10-30 |

`GATE-24` and `FINAL RELEASE` statuses change only under §8.
