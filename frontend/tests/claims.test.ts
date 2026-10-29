import { describe, it, expect } from "vitest";
import { mapClaimState, mapClaimReason, calculateBlockTimeCountdown, parseClaimStruct } from "../src/lib/claims";

describe("F2: Claim State Enum and Block Countdown", () => {
  it("maps integer state values to contract state names", () => {
    expect(mapClaimState(0)).toBe("None");
    expect(mapClaimState(1)).toBe("Pending");
    expect(mapClaimState(2)).toBe("Challenged");
    expect(mapClaimState(3)).toBe("Finalized");
    expect(mapClaimState(4)).toBe("Rejected");
    expect(mapClaimState(5)).toBe("Expired");
    expect(mapClaimState(99)).toBe("None");
  });

  it("maps dispute reasons correctly", () => {
    expect(mapClaimReason(0)).toBe("NONE");
    expect(mapClaimReason(1)).toBe("WRONG_RESULT");
    expect(mapClaimReason(2)).toBe("EVIDENCE_INVALID");
  });

  it("calculates countdown using block time and local elapsed seconds", () => {
    const blockTime = 1700000000;
    const deadline = 1700000120; // 120s later

    const res0 = calculateBlockTimeCountdown(deadline, blockTime, 0);
    expect(res0.isExpired).toBe(false);
    expect(res0.text).toBe("2m 0s");
    expect(res0.remainingSec).toBe(120);

    const res45 = calculateBlockTimeCountdown(deadline, blockTime, 45);
    expect(res45.isExpired).toBe(false);
    expect(res45.text).toBe("1m 15s");
    expect(res45.remainingSec).toBe(75);

    const res120 = calculateBlockTimeCountdown(deadline, blockTime, 120);
    expect(res120.isExpired).toBe(true);
    expect(res120.text).toBe("Expired");
  });

  it("parses tuple/array returned from viem claim()", () => {
    const rawTuple = [
      "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
      1700000120n,
      1, // Pending
      0, // NONE
      "0x0000000000000000000000000000000000000000",
      0n,
      "0x2701f07d2eb0de529ccb283ac9cd1ebb8ed772916b7db0822335d9bcdabbc026",
      "0x7f427d2c66ff24dd70014a717706d17a25d0070d67c16f69cd1ae9f3777a25f0",
      "0x0000000000000000000000000000000000000000000000000000000000000000",
      200000000001n,
      0n,
      "http://127.0.0.1:8000/case-files/0x7f427d2c...",
      "",
    ];

    const claim = parseClaimStruct(1n, rawTuple);
    expect(claim.id).toBe(1n);
    expect(claim.attester).toBe("0x70997970C51812dc3A010C7d01b50e0d17dc79C8");
    expect(claim.stateName).toBe("Pending");
    expect(claim.claimedResidualBadDebt).toBe(200000000001n);
    expect(claim.marketId).toBe("0x2701f07d2eb0de529ccb283ac9cd1ebb8ed772916b7db0822335d9bcdabbc026");
  });
});
