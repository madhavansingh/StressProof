import { describe, it, expect } from "vitest";
import { keccak256 } from "viem";

describe("Frontend Keccak Verification", () => {
  it("hashes empty bytes matching standard vector", () => {
    const emptyBytes = new Uint8Array(0);
    const hash = keccak256(emptyBytes);
    expect(hash).toBe("0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470");
  });
});
