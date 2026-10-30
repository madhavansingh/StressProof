# StressProof — Demo Guide (local Anvil)

Everything here runs on your machine: Anvil (chain 31337), the FastAPI backend and the Next.js frontend.
No Base Sepolia funds are needed. All data is **SYNTHETIC** (`weth-stable-fixture-v1`, 6 synthetic accounts).
Base Sepolia deployment and testnet acceptance are **pending** and are not part of this demo.

Timing: about 10 minutes, plus 2 minutes of waiting for each challenge window.

## Five-minute presentation

Before you start: the stack is running (section 0), MetaMask is on **Anvil Local** with the attester account
(section 0, "MetaMask on Anvil"), and `make watcher` is running in a terminal.

| Time | Do | Say / expected on screen |
|---|---|---|
| 0:00 | Open http://localhost:3000/dashboard | "Protocols act on AI risk analysis nobody can check. StressProof makes every claim bonded and replayable." The dashboard reads the chain live: claims, max LTV (50% after claim #1), circuit breaker, latest bad debt. The amber badge says the dataset is SYNTHETIC |
| 0:45 | Sidebar → **STRESS_SIMULATION**, click **RUN_STRESS_SIMULATION** | 4 liquidatable accounts, debt at risk $33,743.00, liquidation volume $31,743.00, residual bad debt **$2,000.00**, plus an evidence hash. "Integer-only replay: same inputs, same bytes, same hash." |
| 1:30 | Click **PUBLISH_BONDED_CLAIM** and confirm in MetaMask | "CLAIM_POSTED_ON_CHAIN" with the tx hash and claim id. "The attester stakes 0.01 ETH on this number." |
| 2:00 | Open the claim (**VIEW_CLAIM_DOSSIER**) | The browser re-hashes the case file: **KECCAK256 INTEGRITY VERIFIED**. "Anyone can check the evidence; it is content-addressed." |
| 2:30 | In a terminal: `make evil` | A dishonest attester posts an inflated claim. On its next poll, `make watcher` fetches the case file, replays it and challenges. On `/claims` the new claim turns **CHALLENGED** |
| 3:15 | `uv run -m stressproof_agents.resolver.cli resolve <id>` (dry run), then again with `--send` and type `UPHOLD <id>` when asked | The resolver replays the file and prints the decision: **UPHOLD the challenge**. The challenger wins both bonds. "The verdict is the deterministic replay, not a vote." |
| 3:45 | Sidebar → **CIRCUIT_BREAKER** (`/vault`), click **EXECUTE_BORROW_SIMULATION** (70% LTV) | `REVERT: LtvTooHigh(7000, 5000)`. "A finalized claim lowered max LTV from 80% to 50% on chain; the lending market enforces it." |
| 4:15 | Sidebar → **EXPOSURE_GRAPH** | Accounts, assets, market, case file and claims from the replay. Click an account: every value is tagged with its source. "Per-account outputs reproduce every committed total." The TigerGraph panel says **TIGERGRAPH UNAVAILABLE**: the schema exists in Savanna, but data loading is pending |
| 4:45 | Close | "Bonded claims, deterministic replay, on-chain enforcement. Local Anvil today; Base Sepolia deployment is pending." |

If the `make evil` path fails, use the UI path in section 6 instead: challenge from `/claims` with a second
account.

## 0. Start the stack

Terminal 1, the chain. Skip this if Anvil is already running on 8546 with the demo state.

```bash
make chain
```

Terminal 2, contracts. Run this only on a **fresh** chain. Skip it when restoring the saved state (below).

```bash
make deploy-local
```

Terminal 3, backend:

```bash
make backend
```

Terminal 4, frontend:

```bash
cd frontend && npm run dev
```

Optional, terminal 5, the watcher agent (challenges wrong claims automatically):

```bash
make watcher
```

Open http://localhost:3000.

### Restore the saved demo state (optional)

The chain used to prepare this submission has claims #1 (Finalized), #2 (Pending, past its window) and
#3 (Expired), and the vault at 50% max LTV, applied from claim #1. A copy is saved, git-ignored, at
`data/anvil-demo-state-2026-10-30.hex`. To restore it into a freshly started `make chain` (do not run
`make deploy-local` first):

```bash
cast rpc anvil_loadState "$(tr -d '"\n' < data/anvil-demo-state-2026-10-30.hex)" --rpc-url http://127.0.0.1:8546
```

Check it worked: `cast call 0x5FbDB2315678afecb367f032d93F642f64180aa3 "claimCount()(uint256)" --rpc-url http://127.0.0.1:8546` prints `3`.
The case files those claims point to are in the local backend's `data/case-files/`, also git-ignored.

To save the current state again before experimenting:

```bash
cast rpc anvil_dumpState --rpc-url http://127.0.0.1:8546 > data/anvil-demo-state-$(date +%F).hex
```

### MetaMask on Anvil

1. In MetaMask, add a network: name `Anvil Local`, RPC URL `http://127.0.0.1:8546`, chain ID `31337`,
   currency `ETH`.
2. Import one of the test accounts that `anvil` prints when it starts. These are Anvil's public development
   keys: never send real funds to them or use them on any public network.
3. Use the **attester** account (as listed in your local `.env`) to publish, and a different account to
   challenge, because the contract refuses a challenge from the attester (`AttesterCannotChallenge`).
4. If MetaMask shows an old nonce after Anvil restarts, clear its activity for that account
   (Settings → Advanced → Clear activity tab data).

## 1. Landing page and navigation

http://localhost:3000. Show the protocol pipeline (fork → shock → replay → bonded claim → challenge → vault).
**Launch Risk Command Center** opens the dashboard; the sidebar reaches every page.

## 2. Dashboard

`/dashboard` reads the chain and the backend live: monitored market, total claims, active max LTV and
circuit-breaker state, and the recent claims. The header badge states the gate status honestly:
**GATE-24: local pass · testnet pending**.

## 3. Stress simulation

`/stress`: dataset `weth-stable-fixture-v1` (SYNTHETIC banner shown), shock −30%. Click
**RUN_STRESS_SIMULATION**. Expected: 4 liquidatable accounts, debt at risk $33,743.00, liquidation volume
$31,743.00, residual bad debt **$2,000.00**, plus an `evidenceHash` and case-file URI.

## 4. Deterministic replay and evidence check

Open the case-file URI, or check it from a shell (replace the hash with yours):

```bash
H=0x...   # evidenceHash shown on the page
curl -s http://127.0.0.1:8000/case-files/$H -o /tmp/cf.json && cast keccak "$(cat /tmp/cf.json)"
```

The printed hash equals `H`. Running the simulation again with the same inputs produces the same hash.

## 5. Publish a bonded claim (MetaMask)

On `/stress`, connect MetaMask (attester account, Anvil Local) and click **PUBLISH_BONDED_CLAIM
(STAKE 0.01 ETH)**. Confirm in MetaMask. The receipt is checked on chain and the claim appears on `/claims` as
**Pending**, with a 120 s countdown.

## 6. Claims lifecycle

On `/claims` and `/claims/[id]`:

- **Challenge (agents, recommended):** with `make watcher` running, `make evil` posts an inflated claim. The
  watcher replays it, uploads a replay report and challenges automatically.
- **Challenge (UI):** switch MetaMask to another account and click **CHALLENGE** on a Pending claim in
  `/claims`. Choose `WRONG_RESULT` with a counter value, or `EVIDENCE_INVALID`. Give a replay-report URL
  (`http://127.0.0.1:8000/replay-reports/0x…`, for example one the watcher uploaded) and confirm (0.01 ETH bond).
  You must do this within 120 s of publishing. The action is simulated before signing, so a
  predictable revert (window closed, counter equal to the claim, attester challenging their own claim) is explained instead of sent.
- **Resolve:** the designated resolver settles a dispute from the command line.
  `uv run -m stressproof_agents.resolver.cli resolve <id>` is a dry run that prints the replay and the
  decision. Add `--send` to submit it; it asks you to type `UPHOLD <id>` or `REJECT <id>` (`--yes` skips that). `make resolve ID=<id>` runs the dry run. If the claim was right, the
  challenge is rejected and the attester wins 2× bond, and the claim shows **FINALIZED**. If it was wrong, the
  challenge is upheld and the claim shows **REJECTED**.
- **Finalize:** after 120 s with no challenge, **FINALIZE** (any account).
- **Expire:** a challenged claim the resolver did not settle within 300 s can be expired; both bonds are
  refunded.
- **Withdraw:** the credits panel on `/claims` shows the connected account's credited bonds and rewards;
  **Withdraw** pays them out.

Claim #2 in the saved state is past its window, so **FINALIZE** works on it immediately.

## 7. Vault circuit breaker and 50% LTV

`/vault`: max LTV is 50% (default 80%), tightened by claim #1. To apply a newly finalized claim, open it at
`/claims/<id>` and use its apply-to-vault action. `RESET_VAULT_CONTROLS` on `/vault` restores the defaults (demo only). In the borrow simulator, the default request is 70% LTV: **EXECUTE_BORROW_SIMULATION** returns
`REVERT: LtvTooHigh(7000, 5000)`. A request at or below 50% passes. Claims at or above $1,000 residual bad debt
lower the limit; above $4,000 they pause borrowing. The market is a mock.

## 8. Reactive feed

`/feed` polls every 2 s and shows backend entries (stress runs, agent actions) and on-chain registry events,
each labelled with its source. Chain events are authoritative; agent entries are reported, not proven.

## 9. Exposure graph

`/graph` opens the newest claim's evidence. You can also choose another hash, paste one, or open
`/graph?evidence=<hash>`. Show:

- The SYNTHETIC banner.
- The source bar: case file keccak-verified; replay outputs labelled as derived, not on chain.
- Selecting an account: the info panel tags every value REPLAY OUTPUT, CASE FILE or ON CHAIN.
- The outcome filter (bad debt: synth-0002 and synth-0006), search, zoom and pan.
- "Per-account outputs reproduce every committed total."
- The graph informs only; it never affects a verdict.
- Below the graph, the TigerGraph panel shows **TIGERGRAPH UNAVAILABLE**. The schema exists in Savanna, but
  CSV loading is pending, so no live TigerGraph data is connected. Say so; the graph above is local replay.

## 10. Wallet errors and wrong-network protection

- Switch MetaMask to another network and try to publish: the write is refused before anything is signed,
  and the banner offers to switch back to Anvil Local.
- Reject a signature in MetaMask: the page shows "rejected", and nothing is sent.
- Disconnect: write buttons are disabled, and read-only data stays visible.

## Rehearse without losing the demo state

```bash
cast rpc evm_snapshot --rpc-url http://127.0.0.1:8546      # prints an id, e.g. "0x15"
# ... rehearse: publish, challenge, resolve, apply ...
cast rpc evm_revert 0x15 --rpc-url http://127.0.0.1:8546   # back to exactly where you were
```

## What was verified (2026-10-30)

These were exercised through the real UI on local Anvil with an **injected test wallet** backed by Anvil's
dev accounts, then reverted with `evm_revert`. This was **not** the MetaMask extension.

- Stress run and publish (claim #4, evidence hash and tx hash shown).
- In-browser keccak verification.
- Apply refused for a Pending claim (`NotFinalized`, nothing sent).
- Finalize after the window.
- UI challenge (claim #5), resolved with the resolver tool (challenge rejected, attester credited 0.02 ETH).
- Withdraw (credits 0.05 → 0 ETH, balance up by the same amount minus gas).
- Wallet rejection ("Nothing was sent").
- Wrong network: banner shown, write refused, no block mined.
- Apply finalized claim to the vault.
- Borrow at 40% and 50% passes; 51% reverts `LtvTooHigh(5100, 5000)`.

Not re-run in this session: `make evil` + watcher (covered by the GATE-24 local run, 101/101), the expire
path (covered by GATE-24 and the earlier WP-13 check), and the MetaMask extension (owner's manual check).

## If something breaks

| Symptom | Fix |
|---|---|
| Pages show RPC errors | Anvil is not on 8546, or contracts are not deployed (`make deploy-local`) |
| Case file 404 for an old claim | The backend `data/` directory was reset; re-run the stress simulation |
| MetaMask "nonce too high" | Clear activity tab data for the account (see above) |
| Backend 401/403 on publish | `API_WRITE_TOKEN` in `frontend/.env` must match the backend's `.env` |
| Sidebar shows **BACKEND OFFLINE** | Restart it: `make backend` (port 8000) |
| Frontend blank or not loading | `cd frontend && npm run dev`; if port 3000 is taken, stop the old process first |
| Anvil stopped | `make chain`, then restore the saved state (above) or run `make deploy-local` on the fresh chain |
| A challenge reverted "window closed" | The 120 s window passed; publish a new claim and challenge sooner |
