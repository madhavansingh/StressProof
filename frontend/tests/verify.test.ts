import { describe, it, expect } from "vitest";
import { keccak256 } from "viem";
import { verifyEvidenceUri } from "../src/lib/validation/verify";
import { formatUsd8, formatBps, formatCountdown } from "../src/lib/format";

describe("Frontend Verification & Formatting Suite", () => {
  it("hashes empty bytes matching standard Keccak-256 vector", () => {
    const emptyBytes = new Uint8Array(0);
    const hash = keccak256(emptyBytes);
    expect(hash).toBe("0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470");
  });

  it("formats USD 8-decimal integers accurately without float errors", () => {
    expect(formatUsd8("200000000001")).toBe("$2,000.00");
    expect(formatUsd8("3374300000002")).toBe("$33,743.00");
    expect(formatUsd8("0")).toBe("$0.00");
    expect(formatUsd8(BigInt("100000000000000000000"))).toBe("$1,000,000,000,000.00");
    expect(formatUsd8(BigInt("-50000000000"))).toBe("-$500.00");
    expect(formatUsd8(BigInt("-5000000"))).toBe("-$0.05");
  });

  it("formats basis points into percentages correctly", () => {
    expect(formatBps(-3000)).toBe("-30.00%");
    expect(formatBps(8000)).toBe("80.00%");
    expect(formatBps(5000)).toBe("50.00%");
  });

  it("computes countdown text and expiration state", () => {
    const now = Math.floor(Date.now() / 1000);
    const future = now + 90;
    const past = now - 10;

    const futureRes = formatCountdown(future, now);
    expect(futureRes.isExpired).toBe(false);
    expect(futureRes.text).toBe("1m 30s");

    const pastRes = formatCountdown(past, now);
    expect(pastRes.isExpired).toBe(true);
    expect(pastRes.text).toBe("Expired");
  });
});
