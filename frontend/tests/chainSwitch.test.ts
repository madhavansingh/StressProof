import { describe, it, expect } from "vitest";
import { connect, createConfig, createStorage, getAccount, mock, noopStorage, switchChain } from "@wagmi/core";
import { http, SwitchChainError, UserRejectedRequestError } from "viem";
import { baseSepolia, hardhat } from "viem/chains";
import {
  classifySwitchError,
  requestChainSwitch,
  unsupportedSwitchMessage,
  walletLabel,
} from "../src/lib/web3/chainSwitch";
import { checkWriteReadiness } from "../src/lib/web3/walletPolicy";

const ADDR = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC";
const REGISTRY = "0x5FbDB2315678afecb367f032d93F642f64180aa3";
const anvil = { ...hardhat, id: 31337 as const };

describe("classifySwitchError: from the actual error, never the wallet's name", () => {
  it("treats a user rejection as rejected", () => {
    expect(classifySwitchError(new UserRejectedRequestError(new Error("User rejected the request.")))).toBe("rejected");
    expect(classifySwitchError({ code: 4001, message: "User denied" })).toBe("rejected");
  });

  it("treats an unknown or unapproved chain as unsupported", () => {
    expect(classifySwitchError(new SwitchChainError(new Error("Cake Wallet cannot switch to chain 31337")))).toBe("unsupported");
    expect(classifySwitchError({ code: 4902, message: "Unrecognized chain ID" })).toBe("unsupported");
    // wagmi's WalletConnect connector wraps a failed add-chain fallback in UserRejectedRequestError.
    const wrapped = new UserRejectedRequestError(
      new Error("Failed to switch to chain 'eip155:31337'. The chain is not approved or the wallet does not support 'wallet_switchEthereumChain' method.")
    );
    expect(classifySwitchError(wrapped)).toBe("unsupported");
  });

  it("keeps anything else as a plain error", () => {
    expect(classifySwitchError(new Error("socket hang up"))).toBe("error");
  });
});

describe("requestChainSwitch", () => {
  it("reports success", async () => {
    expect(await requestChainSwitch(async () => undefined, 31337, 1000)).toEqual({ status: "switched" });
  });

  it("reports a rejection with a retryable message", async () => {
    const outcome = await requestChainSwitch(
      async () => {
        throw new UserRejectedRequestError(new Error("User rejected."));
      },
      31337,
      1000
    );
    expect(outcome).toMatchObject({ status: "rejected" });
    if (outcome.status === "rejected") expect(outcome.message).toMatch(/transactions stay disabled/i);
  });

  it("reports unsupported when the connector cannot switch at all", async () => {
    expect(await requestChainSwitch(undefined, 31337, 1000)).toEqual({ status: "unsupported" });
  });

  it("reports unsupported for an unknown-chain error", async () => {
    const outcome = await requestChainSwitch(
      async () => {
        throw new SwitchChainError(new Error("Cake Wallet cannot switch to chain 31337"));
      },
      31337,
      1000
    );
    expect(outcome).toEqual({ status: "unsupported" });
  });

  it("stops waiting for a wallet that never answers, without marking it unsupported", async () => {
    const outcome = await requestChainSwitch(() => new Promise(() => {}), 31337, 20);
    expect(outcome).toMatchObject({ status: "no-answer" });
  });
});

describe("messages", () => {
  it("uses the requested wording", () => {
    expect(unsupportedSwitchMessage("Cake Wallet", "Anvil Local")).toBe(
      "Cake Wallet cannot switch to Anvil Local. Use a browser wallet for local testing, or connect Cake Wallet to a supported deployment network."
    );
  });

  it("labels the wallet from RainbowKit's details (wagmi's connector name is the generic WalletConnect)", () => {
    expect(walletLabel({ name: "WalletConnect", rkDetails: { name: "Cake Wallet" } })).toBe("Cake Wallet");
    expect(walletLabel({ name: "MetaMask" })).toBe("MetaMask");
    expect(walletLabel(undefined)).toBe("Your wallet");
  });
});

function browserWallet(switchChainError?: unknown) {
  // The mock wallet starts on the first chain, so it begins on the wrong one (84532).
  const config = createConfig({
    chains: [baseSepolia, anvil],
    connectors: [mock({ accounts: [ADDR], features: switchChainError ? { switchChainError: switchChainError as never } : {} })],
    transports: { [anvil.id]: http("http://127.0.0.1:1"), [baseSepolia.id]: http("http://127.0.0.1:1") },
    storage: createStorage({ storage: noopStorage }),
  });
  const readiness = () => {
    const a = getAccount(config);
    return checkWriteReadiness({
      isConnected: a.isConnected,
      address: a.address,
      walletChainId: a.chainId,
      targetChainId: 31337,
      contractAddress: REGISTRY,
    });
  };
  const doSwitch = (params: { chainId: number }) => switchChain(config, params as { chainId: 31337 | 84532 });
  return { config, readiness, doSwitch };
}

describe("browser wallet (MetaMask-like) on the wrong chain", () => {
  it("switches to 31337, after which writes are allowed", async () => {
    const { config, readiness, doSwitch } = browserWallet();
    await connect(config, { connector: config.connectors[0] });
    expect(readiness()).toMatchObject({ ok: false, kind: "wrong-network" });
    expect(await requestChainSwitch(doSwitch, 31337, 1000)).toEqual({ status: "switched" });
    expect(getAccount(config).chainId).toBe(31337);
    expect(readiness()).toEqual({ ok: true, chainId: 31337 });
  });

  it("stays on the wrong chain with writes blocked when the user rejects", async () => {
    const { config, readiness, doSwitch } = browserWallet(true);
    await connect(config, { connector: config.connectors[0] });
    expect(await requestChainSwitch(doSwitch, 31337, 1000)).toMatchObject({ status: "rejected" });
    expect(getAccount(config).chainId).toBe(84532);
    expect(readiness()).toMatchObject({ ok: false, kind: "wrong-network" });
  });

  it("reports unsupported when the wallet does not know the chain, with writes blocked", async () => {
    const unknownChain = Object.assign(new Error("Unrecognized chain ID 0x7a69"), { code: 4902 });
    const { config, readiness, doSwitch } = browserWallet(unknownChain);
    await connect(config, { connector: config.connectors[0] });
    expect(await requestChainSwitch(doSwitch, 31337, 1000)).toEqual({ status: "unsupported" });
    expect(readiness()).toMatchObject({ ok: false, kind: "wrong-network" });
  });
});

describe("wrongChainBannerMode", () => {
  it("offers a switch until a switch attempt shows the wallet cannot do it, then goes browse-only", async () => {
    const { wrongChainBannerMode } = await import("../src/lib/web3/chainSwitch");
    expect(wrongChainBannerMode(null)).toBe("switch");
    expect(wrongChainBannerMode({ status: "rejected", message: "x" })).toBe("switch");
    expect(wrongChainBannerMode({ status: "no-answer", message: "x" })).toBe("switch");
    expect(wrongChainBannerMode({ status: "unsupported" })).toBe("browse-only");
  });
});
