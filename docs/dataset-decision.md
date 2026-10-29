# Demo dataset decision (H8 / H14)

**Status:** decided, 29 Oct 2026. Owner: Developer 2. Applies to the Phase 1 demo (local and testnet).

## Decision: chosen demo parameters

The demo uses the committed **SYNTHETIC** fixture dataset. No REAL Aave extraction is used for the demo.
This section is the decision. Where each value is actually deployed is in "Deployment state" below.

| Item | Value |
|---|---|
| `datasetId` | `weth-stable-fixture-v1` (`data/fixtures/datasets/weth-stable-fixture-v1/`) |
| `dataClass` | `SYNTHETIC` (6 accounts, ids `synth-0001` to `synth-0006`, implementationplan.md Appendix A) |
| `snapshotHash` | `0x9df1899fbcae4e418753920e0d1bee59eed4cb3d0445d982cbc06807838e199d` |
| Scenario | WETH, `shockBps = -3000` (`FIXED_SCENARIO_SHOCK_BPS`) |
| Honest residual bad debt `R` | `200000000001` (USD × 1e8, about $2,000.00) — **final** |
| `LTV_THRESHOLD_USD8` | `100000000000` (= R // 2) |
| `PAUSE_THRESHOLD_USD8` | `400000000002` (= 2 × R) |
| `REDUCED_LTV_BPS` / `DEFAULT_MAX_LTV_BPS` | `5000` / `8000` |
| Malicious claim in the demo | `3 × R = 600000000003` (would pause borrowing if it finalized) |
| Golden case file | `data/fixtures/casefile_v1.json`, `evidenceHash 0x7f427d2c66ff24dd70014a717706d17a25d0070d67c16f69cd1ae9f3777a25f0` |

Contract constraints these satisfy (`contracts/src/DemoVault.sol`): `0 < LTV_THRESHOLD <= PAUSE_THRESHOLD` and
`REDUCED_LTV_BPS < DEFAULT_MAX_LTV_BPS <= 10000`. A finalized claim with residual `>= PAUSE_THRESHOLD` pauses
borrowing; otherwise one with residual `>= LTV_THRESHOLD` lowers max LTV to `REDUCED_LTV_BPS`. The honest claim
(R) therefore lowers max LTV to 50% and does not pause; the malicious 3R claim would pause if it finalized.

## Deployment state (as of 29 Oct 2026)

| Target | State |
|---|---|
| Backend (`https://stressproof-hvf3.onrender.com`) | Deployed. `/datasets` lists only `weth-stable-fixture-v1` |
| Local Anvil (`deployments/31337.json`) | Matches this decision: `ltvThresholdUsd8 100000000000`, `pauseThresholdUsd8 400000000002`, `reducedLtvBps 5000`, `defaultMaxLtvBps 8000`, `marketId 0x2701f07d2eb0de529ccb283ac9cd1ebb8ed772916b7db0822335d9bcdabbc026` (= `market_id("aave-v3-eth-weth-stable")`) |
| Base Sepolia (`deployments/84532.json`) | **Not deployed.** The file is a placeholder: zero addresses, zero thresholds, and a stale `marketId` that does not equal `market_id("aave-v3-eth-weth-stable")`. The agents reject it as it stands (`agents/.../common/deployments.py` checks the market id), so it cannot be used by mistake |
| `.env.example` | Names the fixture thresholds in comments only; `PAUSE_THRESHOLD_USD8` and `LTV_THRESHOLD_USD8` are blank |

Before the Base Sepolia deployment:

- Set `PAUSE_THRESHOLD_USD8=400000000002`, `LTV_THRESHOLD_USD8=100000000000`, `REDUCED_LTV_BPS=5000`,
  `DEFAULT_MAX_LTV_BPS=8000` and `MARKET_ID_STRING=aave-v3-eth-weth-stable` in the deployer's environment.
  `contracts/script/Deploy.s.sol` reverts on a zero threshold and on thresholds that break the constraints above.
- Run `make deploy-testnet` (`scripts/deploy.sh testnet`). It refuses uncommitted changes and writes
  `deployments/84532.json` only from confirmed receipts and on-chain reads, checking that the vault's
  `MARKET_ID` equals `market_id(MARKET_ID_STRING)`. Do not edit that file by hand.
- Only after that file is regenerated can the agents and frontend use Base Sepolia.

## Why SYNTHETIC

- No mainnet archive RPC is configured, so REAL extraction (`make pin extract normalize sweep`) cannot run
  before the demo. The plan's fallback (implementationplan.md §9.7, spec §17) is a SYNTHETIC dataset.
- The fixture's numbers are pinned by tests in core, pipeline and backend, and by the frontend's hash check, so
  every component already agrees on them.
- `R > 0` and at least two accounts are liquidatable at -3000, so the vault trigger and the dispute both work
  (C-13).

## Consequences

- The UI must show the SYNTHETIC banner: results do not describe real Aave (spec §6.1).
- The demo script must say the shock and thresholds were chosen so the effect is visible (plan §9.8, §12.5).
- Changing the dataset later changes `R`, the thresholds and the contracts' constructor arguments: it needs a
  new sweep, a redeploy and a team announcement.

## Not used for the demo

- `weth-stable-synth-42-v1` (seeded synthetic, R = `11990140000000`) is reproducible locally with
  `synth --seed 42` then `normalize` and `sweep`, but is not committed or deployed.
- REAL extraction is post-demo work: it needs `MAINNET_ARCHIVE_RPC_URL` and `FORK_BLOCK`, then pin, extract,
  normalize and sweep, then new thresholds and a redeploy.
