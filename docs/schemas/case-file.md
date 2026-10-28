# StressProof — Case File Schema

The Case File is the self-contained cryptographic evidence artifact created by an attester and referenced on-chain in `postClaim()`.

Its overall Keccak-256 hash produces `evidenceHash`.

---

## Canonical JSON Structure

```json
{
  "agentRationale": "Phase 1 fixed scenario: -3000 bps WETH shock.",
  "dataClass": "REAL",
  "dataset": {
    "counts": {
      "real": 45,
      "synthetic": 0
    },
    "dataClass": "REAL",
    "datasetId": "weth-stable-19000000-v1",
    "dataProviderAddress": "0x...",
    "excludedCounts": {
      "eMode": 0,
      "noDebt": 12,
      "nonStableDebt": 5,
      "nonWethCollateral": 20,
      "other": 0,
      "wethNotCollateral": 0
    },
    "extractedAt": "2026-10-28T12:00:00Z",
    "extractionScriptCommit": "9a3f2b1...",
    "filter": "collateral=WETH only; debt=stablecoins; eMode=0; isolation=false",
    "forkBlock": 19000000,
    "forkBlockHash": "0x...",
    "forkBlockTimestamp": 1705000000,
    "network": "ethereum-mainnet-fork",
    "oracleAddress": "0x...",
    "poolAddress": "0x...",
    "poolAddressesProvider": "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e",
    "rpcProvider": "Alchemy",
    "snapshotHash": "0x...",
    "stablecoinAllowlist": [
      { "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "symbol": "USDC" }
    ],
    "syntheticSeed": null,
    "wethAddress": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
  },
  "marketId": "aave-v3-eth-weth-stable",
  "model": {
    "id": "static-liquidation-v1",
    "replayerCommit": "9a3f2b1..."
  },
  "results": {
    "debtAtRiskUsd8": "3374300000002",
    "liquidatableAccounts": 4,
    "liquidationVolumeUsd8": "3174300000001",
    "residualBadDebtUsd8": "200000000001"
  },
  "scenario": {
    "asset": "WETH",
    "shockBps": -3000
  },
  "schemaVersion": 1,
  "snapshot": {
    "accounts": [
      {
        "collateralAmount": "10000000000000000000",
        "debtUsd8": "2000000000000",
        "id": "0x0000000000000000000000000000000000000001",
        "origin": "real_aave_v3_fork"
      }
    ],
    "assets": {
      "WETH": {
        "bonusBps": 10500,
        "decimals": 18,
        "ltBps": 8300,
        "priceUsd8": "300000000000"
      }
    }
  }
}
```

---

## Validation Invariants

1. `keccak256(canonical_bytes(snapshot)) == dataset.snapshotHash`.
2. Accounts are sorted ascending by `id`.
3. `results.residualBadDebtUsd8` equals the on-chain `claimedResidualBadDebt`.
4. `model.id` must equal `"static-liquidation-v1"`.
5. `scenario.shockBps` must be an integer between `-9000` and `-1`.
