import { describe, it, expect } from "vitest";
import { deriveWalletRiskProfile, SAMPLE_WALLETS } from "../src/lib/walletRisk";

describe("deriveWalletRiskProfile", () => {
  it("derives different values for different wallet addresses", () => {
    const profileA = deriveWalletRiskProfile("0xd990364d241de18f7dbf17424177b944208a7980");
    const profileB = deriveWalletRiskProfile("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266");
    const profileC = deriveWalletRiskProfile("0x70997970C51812dc3A010C7d01b50e0d17dc79C8");

    // Collateral, debt, or LTV must be distinct across different wallets
    expect(profileA.collateralUsd).not.toBe(profileB.collateralUsd);
    expect(profileA.debtUsd).not.toBe(profileB.debtUsd);
    expect(profileA.role).not.toBe(profileB.role);
    expect(profileC.role).toBe("PROTOCOL_RESOLVER");
    expect(profileB.role).toBe("VAULT_ADMIN");
  });

  it("is deterministic for the same address across calls", () => {
    const addr = "0x1234567890abcdef1234567890abcdef12345678";
    const run1 = deriveWalletRiskProfile(addr);
    const run2 = deriveWalletRiskProfile(addr);

    expect(run1).toEqual(run2);
    expect(run1.collateralUsd).toBe(run2.collateralUsd);
    expect(run1.debtUsd).toBe(run2.debtUsd);
    expect(run1.healthFactor).toBe(run2.healthFactor);
    expect(run1.accountLtvPct).toBe(run2.accountLtvPct);
  });

  it("provides valid defaults when address is undefined or null", () => {
    const profile = deriveWalletRiskProfile(null);
    expect(profile).toBeDefined();
    expect(profile.address).toMatch(/^0x/);
    expect(profile.collateralUsd).toBeGreaterThan(0);
    expect(profile.debtUsd).toBeGreaterThan(0);
    expect(profile.healthFactor).toBeGreaterThan(0);
  });

  it("calculates realistic financial metrics within expected bounds", () => {
    SAMPLE_WALLETS.forEach((sample) => {
      const p = deriveWalletRiskProfile(sample.address);
      expect(p.collateralUsd).toBeGreaterThanOrEqual(10000);
      expect(p.debtUsd).toBeGreaterThan(0);
      expect(p.accountLtvPct).toBeLessThan(100);
      expect(p.healthFactor).toBeGreaterThan(0.5);
      expect(["SAFE", "MODERATE", "AT_RISK", "CRITICAL"]).toContain(p.healthStatus);
    });
  });

  it("allows overriding debt with on-chain values", () => {
    const customDebtUsd8 = 950000000000n; // $9,500.00
    const profile = deriveWalletRiskProfile("0xd990364d241de18f7dbf17424177b944208a7980", {
      onChainDebtUsd8: customDebtUsd8,
    });
    expect(profile.debtUsd).toBe(9500);
  });
});
