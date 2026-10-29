import { describe, it, expect, vi } from "vitest";
import { UserRejectedRequestError } from "viem";
import {
  clearWalletDiagnostic,
  diagnoseConnectError,
  diagnoseConnected,
  getWalletDiagnostic,
  redactAddress,
  reportWalletDiagnostic,
  subscribeWalletDiagnostic,
  summarizeSession,
} from "../src/lib/web3/walletDiagnostics";

const ADDR = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC";
const ctx = { walletName: "Cake Wallet", targetChainId: 31337 };

describe("summarizeSession: redacted shape of a WalletConnect session", () => {
  it("returns null without a session", () => {
    expect(summarizeSession(undefined)).toBeNull();
    expect(summarizeSession(null)).toBeNull();
  });

  it("counts valid eip155 accounts and their chains without keeping addresses or topics", () => {
    const summary = summarizeSession({
      topic: "secret-topic",
      namespaces: {
        eip155: { accounts: [`eip155:1:${ADDR}`, `eip155:137:${ADDR}`, "eip155:1:not-an-address"], methods: ["personal_sign", "eth_sendTransaction"] },
      },
    });
    expect(summary).toEqual({ hasEip155: true, accountCount: 2, invalidAccountCount: 1, accountChainIds: [1, 137], methodCount: 2 });
    expect(JSON.stringify(summary)).not.toContain(ADDR);
    expect(JSON.stringify(summary)).not.toContain("secret-topic");
  });

  it("reports a session without an EVM namespace", () => {
    expect(summarizeSession({ namespaces: { solana: { accounts: ["solana:abc:xyz"] } } })).toMatchObject({
      hasEip155: false,
      accountCount: 0,
    });
  });
});

describe("diagnoseConnected: what a finished connect really authorized", () => {
  const summaryWith = (chains: number[]) => ({
    hasEip155: true,
    accountCount: chains.length,
    invalidAccountCount: 0,
    accountChainIds: chains,
    methodCount: 2,
  });

  it("is connected with an account on the deployment chain", () => {
    expect(diagnoseConnected({ ...ctx, accounts: [ADDR], chainId: 31337, summary: summaryWith([31337]) }).stage).toBe("connected");
  });

  it("is wrong-network with a real account on another chain, and says writes stay disabled", () => {
    const d = diagnoseConnected({ ...ctx, accounts: [ADDR], chainId: 1, summary: summaryWith([1]) });
    expect(d.stage).toBe("wrong-network");
    expect(d.message).toContain("chain 1");
    expect(d.message).toContain("31337");
    expect(d.message).toMatch(/transactions stay disabled/i);
  });

  it("is no-account when the session approved no EVM account", () => {
    const d = diagnoseConnected({ ...ctx, accounts: [], chainId: 31337, summary: summaryWith([]) });
    expect(d.stage).toBe("no-account");
    expect(d.message).toMatch(/paired but did not share an EVM account/i);
  });

  it("is no-evm-namespace when the session has no eip155 namespace", () => {
    const d = diagnoseConnected({
      ...ctx,
      accounts: [],
      chainId: 31337,
      summary: { hasEip155: false, accountCount: 0, invalidAccountCount: 0, accountChainIds: [], methodCount: 0 },
    });
    expect(d.stage).toBe("no-evm-namespace");
  });
});

describe("diagnoseConnectError: safe messages per lifecycle stage", () => {
  it("rejection", () => {
    const d = diagnoseConnectError(new UserRejectedRequestError(new Error("User rejected.")), { ...ctx, summary: null });
    expect(d.stage).toBe("rejected");
    expect(d.message).toMatch(/nothing was sent/i);
  });

  it("an expired proposal gets its own stage and asks for a new QR code", () => {
    const d = diagnoseConnectError(new Error("Proposal expired"), { ...ctx, summary: null });
    expect(d.stage).toBe("expired");
    expect(d.message).toBe("Connection request expired. Generate a new QR code and scan again.");
  });

  it("a pairing closed before approval is reported as no session", () => {
    expect(diagnoseConnectError(new Error("Connection request reset. Please try again."), { ...ctx, summary: null }).stage)
      .toBe("no-session");
  });

  it("anything else keeps a short message and never succeeds", () => {
    const d = diagnoseConnectError(new Error("relay socket closed"), { ...ctx, summary: null });
    expect(d.stage).toBe("error");
    expect(d.message).toContain("relay socket closed");
  });

  it("never echoes a pairing URI or project ID found in an error", () => {
    const leaky = new Error("failed for wc:abcdef@2?relay-protocol=irn&symKey=deadbeef projectId=0123456789abcdef0123456789abcdef");
    const d = diagnoseConnectError(leaky, { ...ctx, summary: null });
    expect(d.message).not.toContain("symKey");
    expect(d.message).not.toContain("deadbeef");
    expect(d.message).not.toContain("0123456789abcdef0123456789abcdef");
  });
});

describe("diagnostic store", () => {
  it("notifies subscribers and clears", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeWalletDiagnostic(listener);
    const d = diagnoseConnectError(new Error("relay closed"), { ...ctx, summary: null });
    reportWalletDiagnostic(d);
    expect(getWalletDiagnostic()).toBe(d);
    clearWalletDiagnostic();
    expect(getWalletDiagnostic()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it("redacts addresses for display in diagnostics", () => {
    expect(redactAddress(ADDR)).toBe("0x3C44…93BC");
  });
});

describe("connection timing (numbers only)", () => {
  it("measures approval to visible once, and only after an approval", async () => {
    const { markWalletVisible, noteSessionApproved, noteSessionValidated, getWalletTiming, resetWalletTiming } =
      await import("../src/lib/web3/walletDiagnostics");
    resetWalletTiming();
    markWalletVisible(5);
    expect(getWalletTiming().visibleAt).toBeUndefined();
    noteSessionApproved(100);
    noteSessionValidated(104);
    markWalletVisible(130);
    markWalletVisible(900);
    expect(getWalletTiming()).toEqual({ approvedAt: 100, validatedAt: 104, visibleAt: 130, approvalToVisibleMs: 30 });
  });
});
