import { describe, it, expect } from "vitest";
import {
  UNAVAILABLE,
  formatLtvBps,
  formatPaused,
  ltvStatusLabel,
  parseVaultReading,
  vaultConfig,
} from "../src/lib/vaultDisplay";

describe("vault display: never shows defaults as live state", () => {
  it("formats a real reading and reports UNAVAILABLE when there is none", () => {
    expect(formatLtvBps(5000)).toBe("50.00%");
    expect(formatLtvBps(null)).toBe(UNAVAILABLE);
    expect(formatPaused(true, "HALTED", "OPERATIONAL")).toBe("HALTED");
    expect(formatPaused(false, "HALTED", "OPERATIONAL")).toBe("OPERATIONAL");
    expect(formatPaused(null, "HALTED", "OPERATIONAL")).toBe(UNAVAILABLE);
  });

  it("labels the LTV against the deployment's configured values, not constants", () => {
    const cfg = vaultConfig(31337);
    expect(cfg.defaultMaxLtvBps).toBe(8000);
    expect(cfg.reducedLtvBps).toBe(5000);
    expect(ltvStatusLabel(5000, cfg)).toBe("TIGHTENED (default 80.00%)");
    expect(ltvStatusLabel(8000, cfg)).toBe("DEFAULT");
    expect(ltvStatusLabel(null, cfg)).toBe(UNAVAILABLE);
  });

  it("takes thresholds from deployments/31337.json", () => {
    const cfg = vaultConfig(31337);
    expect(cfg.ltvThresholdUsd8).toBe(100000000000n);
    expect(cfg.pauseThresholdUsd8).toBe(400000000002n);
  });

  it("reports thresholds as unknown for the placeholder testnet deployment", () => {
    const cfg = vaultConfig(84532);
    expect(cfg.ltvThresholdUsd8).toBeNull();
    expect(cfg.pauseThresholdUsd8).toBeNull();
  });

  it("parses contract return values and rejects malformed ones", () => {
    expect(parseVaultReading(5000, false, 1n)).toEqual({ maxLtvBps: 5000, borrowPaused: false, lastAppliedClaimId: 1n });
    expect(parseVaultReading(8000n, true, 0n)).toEqual({ maxLtvBps: 8000, borrowPaused: true, lastAppliedClaimId: 0n });
    expect(() => parseVaultReading("8000", false, 0n)).toThrow();
    expect(() => parseVaultReading(8000, "false", 0n)).toThrow();
    expect(() => parseVaultReading(8000, false, -1n)).toThrow();
    expect(() => parseVaultReading(10001, false, 0n)).toThrow();
  });
});
