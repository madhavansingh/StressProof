# StressProof Contracts

Foundry project containing smart contracts for StressProof:
* `StressRegistry.sol`: Permissionless registry managing bonded risk claims, dispute challenges, resolution, and pull payments.
* `DemoVault.sol`: Consumer vault executing bounded risk parameter adjustments (pause, reduced max LTV) upon finalized claims.
* `MockLendingMarket.sol`: Mock market demonstrating transaction failure (`LtvTooHigh`, `BorrowPaused`) when risk limits are breached.

## Developer 3 Commands
```bash
# Run test suite
forge test

# Run balance accounting invariant tests
forge test --match-contract Invariant

# Deploy locally
forge script script/Deploy.s.sol:Deploy --rpc-url http://127.0.0.1:8546 --broadcast

# Export ABIs to frontend and agents
bash ../scripts/export_abis.sh
```
