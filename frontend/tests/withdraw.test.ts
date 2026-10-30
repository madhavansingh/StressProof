import { describe, it, expect } from "vitest";
import { withdrawPlan } from "../src/lib/web3/withdraw";

const REGISTRY = "0x5FbDB2315678afecb367f032d93F642f64180aa3";
const ACCOUNT = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC";
const ready = { isConnected: true, address: ACCOUNT, walletChainId: 31337, targetChainId: 31337, registry: REGISTRY };

describe("withdrawPlan: pull payments are collected only by a connected wallet on the deployment chain", () => {
  it("allows withdrawing a positive credit and pins the deployment chain", () => {
    expect(withdrawPlan({ ...ready, credits: 10_000_000_000_000_000n })).toEqual({ ok: true, chainId: 31337 });
  });

  it("refuses when there is nothing credited", () => {
    const plan = withdrawPlan({ ...ready, credits: 0n });
    expect(plan.ok).toBe(false);
    if (!plan.ok) expect(plan.message).toMatch(/nothing to withdraw/i);
  });

  it("refuses while the credit is still unknown", () => {
    expect(withdrawPlan({ ...ready, credits: undefined }).ok).toBe(false);
  });

  it("refuses without a wallet, on the wrong chain, or without a deployment", () => {
    expect(withdrawPlan({ ...ready, isConnected: false, credits: 1n })).toMatchObject({ ok: false });
    expect(withdrawPlan({ ...ready, walletChainId: 1, credits: 1n })).toMatchObject({ ok: false });
    expect(withdrawPlan({ ...ready, registry: "0x0000000000000000000000000000000000000000", credits: 1n })).toMatchObject({ ok: false });
  });
});
