import { describe, it, expect } from "vitest";
import { encodeErrorResult } from "viem";
import { decodeContractError } from "../src/lib/web3/errors";
import { MockLendingMarketAbi, DemoVaultAbi } from "../src/lib/contracts";

describe("F4: Contract Error Decoding and §19.4 Sentences", () => {
  it("encodes and decodes LtvTooHigh(7000, 5000) with 0x37e4c1c4 selector", () => {
    const encoded = encodeErrorResult({
      abi: MockLendingMarketAbi as any,
      errorName: "LtvTooHigh",
      args: [7000n, 5000n],
    });

    expect(encoded.startsWith("0x37e4c1c4")).toBe(true);

    const decoded = decodeContractError(encoded);
    expect(decoded.errorName).toBe("LtvTooHigh");
    expect(decoded.userMessage).toContain("LtvTooHigh(7000, 5000)");
    expect(decoded.userMessage).toContain("Borrow would exceed vault max LTV of 50.00%");
  });

  it("encodes and decodes NotFinalized() with 0x1bee0d5a selector", () => {
    const encoded = encodeErrorResult({
      abi: DemoVaultAbi as any,
      errorName: "NotFinalized",
    });

    expect(encoded.startsWith("0x1bee0d5a")).toBe(true);

    const decoded = decodeContractError(encoded);
    expect(decoded.errorName).toBe("NotFinalized");
    expect(decoded.userMessage).toBe("Only finalized claims can change the vault");
  });

  it("encodes and decodes BorrowPaused()", () => {
    const encoded = encodeErrorResult({
      abi: MockLendingMarketAbi as any,
      errorName: "BorrowPaused",
    });

    const decoded = decodeContractError(encoded);
    expect(decoded.errorName).toBe("BorrowPaused");
    expect(decoded.userMessage).toBe("Borrowing is paused by the circuit breaker");
  });

  it("decodes viem structured error object with cause.data", () => {
    const errorObj = {
      cause: {
        data: "0x1bee0d5a",
      },
      message: "execution reverted",
    };

    const decoded = decodeContractError(errorObj);
    expect(decoded.errorName).toBe("NotFinalized");
    expect(decoded.userMessage).toBe("Only finalized claims can change the vault");
  });
});


describe("Registry errors met by challenge and withdraw read clearly", () => {
  it.each([
    ["CounterEqualsClaim", "different result"],
    ["AttesterCannotChallenge", "own claim"],
    ["NothingToWithdraw", "no credited balance"],
  ])("%s", async (errorName, phrase) => {
    const { IStressRegistryAbi } = await import("../src/lib/contracts");
    const data = encodeErrorResult({ abi: IStressRegistryAbi, errorName } as never);
    const decoded = decodeContractError({ data });
    expect(decoded.errorName).toBe(errorName);
    expect(decoded.userMessage).toContain(errorName);
    expect(decoded.userMessage).toContain(phrase);
  });
});
