import { describe, it, expect, vi } from "vitest";
import { encodeErrorResult, type Hex } from "viem";
import { fetchReceiptOutcome, type ReceiptClient } from "../src/lib/web3/txReceipt";
import { IStressRegistryAbi } from "../src/lib/contracts";

const HASH: Hex = `0x${"ab".repeat(32)}`;
const TX = {
  from: "0x90F79bf6EB2c4f870365E785982E1f101E93b906" as Hex,
  to: "0x5FbDB2315678afecb367f032d93F642f64180aa3" as Hex,
  input: "0x8838fb68" as Hex,
  value: 10_000_000_000_000_000n,
};

function client(status: "success" | "reverted", callError?: unknown) {
  const c = {
    waitForTransactionReceipt: vi.fn(async () => ({ status, blockNumber: 8n, transactionHash: HASH }) as never),
    getTransaction: vi.fn(async () => TX as never),
    call: vi.fn(async () => {
      if (callError) throw callError;
      return { data: "0x" };
    }),
  };
  return c as unknown as ReceiptClient & { call: typeof c.call };
}

describe("fetchReceiptOutcome: a mined transaction is reported as success or reverted, never as pending", () => {
  it("returns success receipts without replaying them", async () => {
    const c = client("success");
    const outcome = await fetchReceiptOutcome(c, HASH);
    expect(outcome.status).toBe("success");
    expect(outcome.revertReason).toBeUndefined();
    expect(c.call).not.toHaveBeenCalled();
  });

  it("returns reverted receipts (wagmi's receipt hook throws instead) with the decoded reason", async () => {
    const data = encodeErrorResult({ abi: IStressRegistryAbi, errorName: "CounterEqualsClaim" } as never);
    const c = client("reverted", { data });
    const outcome = await fetchReceiptOutcome(c, HASH);
    expect(outcome.status).toBe("reverted");
    expect(outcome.revertReason).toContain("CounterEqualsClaim");
    // The replay runs against the state just before the transaction's block.
    expect(c.call).toHaveBeenCalledWith(expect.objectContaining({ account: TX.from, to: TX.to, data: TX.input, value: TX.value, blockNumber: 7n }));
  });

  it("explains a revert that the previous block does not reproduce (state or time changed in between)", async () => {
    // Seen on local Anvil: a challenge passed simulation, then was mined after its window closed.
    const c = client("reverted");
    const outcome = await fetchReceiptOutcome(c, HASH);
    expect(outcome.status).toBe("reverted");
    expect(outcome.revertReason).toMatch(/changed between the check and mining/i);
  });

  it("still reports a revert when the replay itself fails for another reason", async () => {
    const c = client("reverted", new Error("socket hang up"));
    const outcome = await fetchReceiptOutcome(c, HASH);
    expect(outcome.status).toBe("reverted");
    expect(outcome.revertReason).toBeUndefined();
  });
});
