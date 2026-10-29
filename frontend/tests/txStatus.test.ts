import { describe, it, expect } from "vitest";
import { txPhase, txPhaseLabel } from "../src/lib/web3/txStatus";

describe("transaction phase reporting", () => {
  it("never calls a simulation or a submitted hash a mined transaction", () => {
    expect(txPhase({ simulationPassed: true, awaitingSignature: false })).toBe("simulation-passed");
    expect(txPhase({ simulationPassed: true, awaitingSignature: true })).toBe("awaiting-signature");
    expect(txPhase({ simulationPassed: true, awaitingSignature: false, hash: "0xabc" })).toBe("submitted");
  });

  it("distinguishes a mined success from a mined revert", () => {
    expect(txPhase({ simulationPassed: true, awaitingSignature: false, hash: "0xabc", receiptStatus: "success" }))
      .toBe("mined-success");
    expect(txPhase({ simulationPassed: true, awaitingSignature: false, hash: "0xabc", receiptStatus: "reverted" }))
      .toBe("mined-reverted");
    expect(txPhaseLabel("mined-reverted")).toBe("MINED: REVERTED");
    expect(txPhaseLabel("simulation-passed")).toContain("NOTHING SENT");
  });

  it("is idle before anything happens", () => {
    expect(txPhase({ simulationPassed: false, awaitingSignature: false })).toBe("idle");
  });
});
