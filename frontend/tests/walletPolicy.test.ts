import { describe, it, expect } from "vitest";
import { UserRejectedRequestError, ChainMismatchError, BaseError } from "viem";
import { anvil, base } from "viem/chains";
import {
  CAKE_WALLET_WALLETCONNECT_CHAIN_IDS,
  cakeWalletSupportsChain,
  checkWriteReadiness,
  describeWalletError,
  walletConnectProjectId,
} from "../src/lib/web3/walletPolicy";

const REGISTRY = "0x5FbDB2315678afecb367f032d93F642f64180aa3";
const ACCOUNT = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC";
const base_ = { isConnected: true, address: ACCOUNT, walletChainId: 31337, targetChainId: 31337, contractAddress: REGISTRY };

describe("Cake Wallet chain support (official docs)", () => {
  it("covers Ethereum, Polygon, Base, Arbitrum, BNB Smart Chain and Robinhood Chain only", () => {
    expect([...CAKE_WALLET_WALLETCONNECT_CHAIN_IDS].sort((a, b) => a - b)).toEqual([1, 56, 137, 4663, 8453, 42161]);
    expect(cakeWalletSupportsChain(8453)).toBe(true);
    expect(cakeWalletSupportsChain(31337)).toBe(false);
    expect(cakeWalletSupportsChain(84532)).toBe(false);
  });
});

describe("WalletConnect project ID", () => {
  it("treats empty values and placeholders as not configured", () => {
    expect(walletConnectProjectId(undefined)).toBeNull();
    expect(walletConnectProjectId("")).toBeNull();
    expect(walletConnectProjectId("  ")).toBeNull();
    expect(walletConnectProjectId("demo_project_id")).toBeNull();
    expect(walletConnectProjectId("YOUR_PROJECT_ID")).toBeNull();
    expect(walletConnectProjectId(" 0123456789abcdef0123456789abcdef ")).toBe("0123456789abcdef0123456789abcdef");
  });
});

describe("checkWriteReadiness: connection and chain before every write", () => {
  it("allows a connected wallet on the deployment chain and pins that chain", () => {
    expect(checkWriteReadiness(base_)).toEqual({ ok: true, chainId: 31337 });
  });

  it("refuses when no wallet is connected or the account is missing", () => {
    expect(checkWriteReadiness({ ...base_, isConnected: false })).toMatchObject({ ok: false, kind: "disconnected" });
    expect(checkWriteReadiness({ ...base_, address: undefined })).toMatchObject({ ok: false, kind: "disconnected" });
  });

  it("refuses a wallet on another chain", () => {
    const r = checkWriteReadiness({ ...base_, walletChainId: 84532 });
    expect(r).toMatchObject({ ok: false, kind: "wrong-network" });
    if (!r.ok) expect(r.message).toContain("chain 84532");
  });

  it("explains the Cake Wallet limitation when the wallet sits on a Cake-supported chain", () => {
    const r = checkWriteReadiness({ ...base_, walletChainId: base.id });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.message).toContain("Cake Wallet cannot switch to this chain");
  });

  it("refuses when the deployment has no contract (placeholder zero address)", () => {
    expect(checkWriteReadiness({ ...base_, contractAddress: "0x0000000000000000000000000000000000000000" }))
      .toMatchObject({ ok: false, kind: "no-deployment" });
    expect(checkWriteReadiness({ ...base_, contractAddress: undefined })).toMatchObject({ ok: false, kind: "no-deployment" });
  });

  it("handles an unknown wallet chain", () => {
    expect(checkWriteReadiness({ ...base_, walletChainId: undefined })).toMatchObject({ ok: false, kind: "wrong-network" });
  });
});

describe("describeWalletError", () => {
  it("reports a rejected request (viem error and raw EIP-1193 code 4001)", () => {
    const viemRejection = new UserRejectedRequestError(new Error("User rejected the request."));
    expect(describeWalletError(viemRejection)).toMatchObject({ kind: "rejected" });
    expect(describeWalletError({ code: 4001, message: "User denied" })).toMatchObject({ kind: "rejected" });
    const wrapped = new BaseError("Write failed", { cause: viemRejection });
    expect(describeWalletError(wrapped).message).toBe("Request rejected in the wallet. Nothing was sent.");
  });

  it("reports a chain mismatch", () => {
    const mismatch = new ChainMismatchError({ chain: anvil, currentChainId: 1 });
    expect(describeWalletError(mismatch)).toMatchObject({ kind: "wrong-network" });
  });

  it("reports a disconnected wallet from wagmi's error name", () => {
    const err = Object.assign(new Error("Connector not connected."), { name: "ConnectorNotConnectedError" });
    expect(describeWalletError(err)).toMatchObject({ kind: "disconnected" });
  });

  it("falls back to the error's own short message, never to success", () => {
    const r = describeWalletError(new Error("insufficient funds for gas"));
    expect(r.kind).toBe("other");
    expect(r.message).toContain("insufficient funds");
  });
});
