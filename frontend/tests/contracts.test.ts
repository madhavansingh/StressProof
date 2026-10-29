import { describe, it, expect } from "vitest";
import { getContractConfig, MockLendingMarketAbi, DemoVaultAbi, IStressRegistryAbi } from "../src/lib/contracts";

describe("F1: Contract Configuration and ABIs", () => {
  it("picks 31337 configuration with correct deployment values", () => {
    const config = getContractConfig(31337);
    expect(config.chainId).toBe(31337);
    expect(config.marketId).toBe("0x2701f07d2eb0de529ccb283ac9cd1ebb8ed772916b7db0822335d9bcdabbc026");
    expect(config.registry.address).toBe("0x5FbDB2315678afecb367f032d93F642f64180aa3");
    expect(config.vault.address).toBe("0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512");
    expect(config.market.address).toBe("0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0");
    expect(config.bondWei).toBe(10000000000000000n);
    expect(config.challengeWindowSec).toBe(120);
    expect(config.resolutionWindowSec).toBe(300);
  });

  it("picks 84532 configuration", () => {
    const config = getContractConfig(84532);
    expect(config.chainId).toBe(84532);
    expect(config.marketId).toBe("0x40d51381e4b3e8a71bbbf288e285817d4567c9c0f99b2eb8c15682fa08d3c7c2");
  });

  it("ABI contains LtvTooHigh custom error in MockLendingMarket", () => {
    const ltvError = (MockLendingMarketAbi as any[]).find(
      (item) => item.type === "error" && item.name === "LtvTooHigh"
    );
    expect(ltvError).toBeDefined();
    expect(ltvError.inputs).toHaveLength(2);
    expect(ltvError.inputs[0].name).toBe("requestedBps");
    expect(ltvError.inputs[1].name).toBe("maxBps");
  });

  it("ABI contains NotFinalized custom error in DemoVault", () => {
    const notFinalizedError = (DemoVaultAbi as any[]).find(
      (item) => item.type === "error" && item.name === "NotFinalized"
    );
    expect(notFinalizedError).toBeDefined();
  });

  it("ABI contains custom errors in IStressRegistry", () => {
    const wrongBondError = (IStressRegistryAbi as any[]).find(
      (item) => item.type === "error" && item.name === "WrongBond"
    );
    expect(wrongBondError).toBeDefined();
  });
});

