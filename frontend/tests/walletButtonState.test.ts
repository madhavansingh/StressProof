import { describe, it, expect } from "vitest";
import {
  landingConnectOutcome,
  walletButtonState,
  type WalletButtonInput,
} from "../src/lib/web3/walletButtonState";

const ACCOUNT = { displayName: "0x3C44…93BC" };
const base: WalletButtonInput = { mounted: true, status: "disconnected", targetChainId: 31337 };

describe("walletButtonState: one state for every wallet button", () => {
  it("renders nothing account-like before mount", () => {
    expect(walletButtonState({ ...base, mounted: false })).toEqual({ kind: "loading" });
  });

  it("is disconnected without an account, even if a stale chain is present", () => {
    expect(walletButtonState(base)).toEqual({ kind: "disconnected" });
    expect(walletButtonState({ ...base, chain: { id: 31337 } })).toEqual({ kind: "disconnected" });
  });

  it("shows connecting and reconnecting as connecting", () => {
    expect(walletButtonState({ ...base, status: "connecting" })).toEqual({ kind: "connecting" });
    expect(walletButtonState({ ...base, status: "reconnecting" })).toEqual({ kind: "connecting" });
  });

  it("flags a wallet on another or unsupported chain as wrong network", () => {
    const connected = { ...base, status: "connected" as const, account: ACCOUNT };
    expect(walletButtonState({ ...connected, chain: { id: 1 } })).toEqual({ kind: "wrong-network", chainId: 1 });
    expect(walletButtonState({ ...connected, chain: { id: 31337, unsupported: true } })).toEqual({
      kind: "wrong-network",
      chainId: 31337,
    });
  });

  it("shows only the real account's display name when on the deployment chain", () => {
    expect(walletButtonState({ ...base, status: "connected", account: ACCOUNT, chain: { id: 31337 } })).toEqual({
      kind: "connected",
      displayName: "0x3C44…93BC",
    });
  });
});

describe("landingConnectOutcome: when the landing page enters the dashboard", () => {
  it("does nothing unless the visitor asked to connect from the landing page", () => {
    expect(landingConnectOutcome({ requested: false, modalOpen: false, state: { kind: "connected", displayName: "x" } }))
      .toBe("idle");
  });

  it("enters the dashboard after a connection the visitor started, on any chain", () => {
    expect(landingConnectOutcome({ requested: true, modalOpen: true, state: { kind: "connected", displayName: "x" } }))
      .toBe("enter-dashboard");
    expect(landingConnectOutcome({ requested: true, modalOpen: false, state: { kind: "wrong-network", chainId: 1 } }))
      .toBe("enter-dashboard");
  });

  it("waits while the modal is open or the wallet is still connecting", () => {
    expect(landingConnectOutcome({ requested: true, modalOpen: true, state: { kind: "disconnected" } })).toBe("idle");
    expect(landingConnectOutcome({ requested: true, modalOpen: false, state: { kind: "connecting" } })).toBe("idle");
  });

  it("reports not connected when the modal closes without a connection (rejected or dismissed)", () => {
    expect(landingConnectOutcome({ requested: true, modalOpen: false, state: { kind: "disconnected" } }))
      .toBe("not-connected");
  });
});

describe("walletButtonState: connection_error with retry", () => {
  const error = { message: "Cake Wallet paired but did not share an EVM account for this app." };

  it("shows the error instead of a plain connect button after a failed attempt", () => {
    expect(walletButtonState({ ...base, error })).toEqual({ kind: "connection-error", message: error.message });
  });

  it("never lets an old error hide a live connection or an attempt in progress", () => {
    expect(walletButtonState({ ...base, status: "connecting", error })).toEqual({ kind: "connecting" });
    expect(
      walletButtonState({ ...base, status: "connected", account: ACCOUNT, chain: { id: 31337 }, error })
    ).toEqual({ kind: "connected", displayName: ACCOUNT.displayName });
  });

  it("lets the landing page react to a failed attempt it started", () => {
    expect(landingConnectOutcome({ requested: true, modalOpen: false, state: { kind: "connection-error", message: "x" } }))
      .toBe("not-connected");
  });
});
