import { describe, it, expect } from "vitest";
import { encodeErrorResult, type Abi } from "viem";
import { chainNowSec, claimActions, nextBlockTimeSec } from "@/lib/claims";
import { simulateAtNextBlock } from "@/lib/web3/simulateAtNextBlock";

const claim = { stateName: "Pending" as const, challengeDeadline: 1_000n, resolutionDeadline: 0n };

describe("chain time on a quiet local chain", () => {
  it("uses the wall clock when the latest block is stale", () => {
    // Latest block at 900, but 5 minutes of wall time have passed with no new block.
    const now = chainNowSec(900, 1_200);
    expect(now).toBe(1_200);
    expect(claimActions(claim, now)).toEqual({ challenge: false, finalize: true, expire: false });
    // The old calculation (block time only) kept the challenge window open: the bug this fixes.
    expect(claimActions(claim, 900).challenge).toBe(true);
  });

  it("never goes back before the latest block", () => {
    expect(chainNowSec(1_500, 1_200)).toBe(1_500);
    expect(nextBlockTimeSec(1_500, 1_200)).toBe(1_501);
    expect(nextBlockTimeSec(900, 1_200.9)).toBe(1_200);
  });
});

const ABI = [
  { type: "function", name: "finalize", stateMutability: "nonpayable", inputs: [{ name: "id", type: "uint256" }], outputs: [] },
  { type: "error", name: "ChallengeWindowOpen", inputs: [] },
] as const satisfies Abi;
const REQ = { account: "0x90F79bf6EB2c4f870365E785982E1f101E93b906", address: "0x5FbDB2315678afecb367f032d93F642f64180aa3", abi: ABI, functionName: "finalize", args: [4n] } as const;

describe("simulateAtNextBlock", () => {
  it("simulates at the next block's timestamp", async () => {
    const calls: Array<Record<string, unknown>> = [];
    const client = { getBlock: async () => ({ timestamp: 900n }), call: async (p: Record<string, unknown>) => { calls.push(p); return { data: "0x" }; } };
    await simulateAtNextBlock(client as never, REQ as never, 1_200);
    expect(calls).toHaveLength(1);
    expect(calls[0].blockOverrides).toEqual({ time: 1_200n });
    expect(calls[0].to).toBe(REQ.address);
  });

  it("passes a revert through for decoding", async () => {
    const revert = Object.assign(new Error("execution reverted"), { data: encodeErrorResult({ abi: ABI, errorName: "ChallengeWindowOpen" }) });
    const client = { getBlock: async () => ({ timestamp: 900n }), call: async () => { throw revert; } };
    await expect(simulateAtNextBlock(client as never, REQ as never, 950)).rejects.toBe(revert);
  });

  it("falls back to a plain call when block overrides are unsupported", async () => {
    const calls: Array<Record<string, unknown>> = [];
    const client = {
      getBlock: async () => ({ timestamp: 900n }),
      call: async (p: Record<string, unknown>) => { calls.push(p); if (p.blockOverrides) throw new Error("invalid params: blockOverrides"); return { data: "0x" }; },
    };
    await simulateAtNextBlock(client as never, REQ as never, 1_200);
    expect(calls.map((c) => "blockOverrides" in c)).toEqual([true, false]);
  });
});
