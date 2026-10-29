import { describe, it, expect, vi } from "vitest";
import fs from "fs";
import path from "path";
import { keccak256 } from "viem";
import {
  verifyEvidenceUri,
  verifyBytes,
  resolveUri,
} from "../src/lib/validation/verify";
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

  it("rewrites ipfs:// URIs to gateway URL per §19.3", () => {
    const uri = "ipfs://bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi";
    const resolved = resolveUri(uri, "https://ipfs.io");
    expect(resolved).toBe("https://ipfs.io/ipfs/bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi");

    const httpUri = "http://127.0.0.1:8000/case-files/0x123";
    expect(resolveUri(httpUri)).toBe(httpUri);
  });

  describe("T-F-03: Evidence Hash Integrity Checks", () => {
    const fixturePath = path.resolve(__dirname, "../../data/fixtures/casefile_v1.json");
    const keccakPath = path.resolve(__dirname, "../../data/fixtures/casefile_v1.keccak");

    const rawFileBytes = fs.readFileSync(fixturePath);
    const expectedHash = fs.readFileSync(keccakPath, "utf-8").trim();

    it("verifies fixture data/fixtures/casefile_v1.json matches data/fixtures/casefile_v1.keccak", () => {
      const res = verifyBytes(new Uint8Array(rawFileBytes), expectedHash);
      expect(res.valid).toBe(true);
      expect(res.computedHash.toLowerCase()).toBe(expectedHash.toLowerCase());
      expect(res.error).toBeUndefined();
    });

    it("fails verification if even one byte changes (one changed byte -> valid: false)", () => {
      const tamperedBytes = new Uint8Array(rawFileBytes);
      // Flip a single byte in the buffer
      tamperedBytes[0] = tamperedBytes[0] === 0 ? 1 : 0;

      const res = verifyBytes(tamperedBytes, expectedHash);
      expect(res.valid).toBe(false);
      expect(res.computedHash.toLowerCase()).not.toBe(expectedHash.toLowerCase());
    });

    it("handles HTTP 404 with error reason and valid: false", async () => {
      // Mock global fetch returning 404
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: "Not Found",
      });

      try {
        const res = await verifyEvidenceUri("http://127.0.0.1:8000/case-files/missing", expectedHash);
        expect(res.valid).toBe(false);
        expect(res.error).toContain("HTTP 404");
      } finally {
        global.fetch = originalFetch;
      }
    });
  });
});
