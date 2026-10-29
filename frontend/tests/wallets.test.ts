import { describe, it, expect } from "vitest";
import { buildWalletList, cakeWallet, CAKE_WALLET_DOCS_URL } from "../src/lib/web3/wallets";

const PROJECT_ID = "0123456789abcdef0123456789abcdef";

describe("wallet list", () => {
  it("offers only the browser wallet when no WalletConnect project ID is configured", () => {
    const groups = buildWalletList(null);
    expect(groups).toHaveLength(1);
    expect(groups[0].wallets).toHaveLength(1);
    const names = groups.flatMap((g) => g.wallets.map((w) => w({ projectId: "unused", appName: "StressProof" }).name));
    expect(names).not.toContain("Cake Wallet");
  });

  it("lists Cake Wallet first when a project ID is configured", () => {
    const groups = buildWalletList(PROJECT_ID);
    const first = groups[0].wallets[0]({ projectId: PROJECT_ID, appName: "StressProof" });
    expect(first.name).toBe("Cake Wallet");
    expect(groups.flatMap((g) => g.wallets)).toHaveLength(3);
  });
});

describe("Cake Wallet entry", () => {
  it("connects over WalletConnect with the plain wc: URI for QR and mobile, and links the official docs", () => {
    const wallet = cakeWallet({ projectId: PROJECT_ID });
    const uri = "wc:abc@2?relay-protocol=irn&symKey=xyz";
    expect(wallet.id).toBe("cake-wallet");
    expect(wallet.qrCode?.getUri(uri)).toBe(uri);
    expect(wallet.mobile?.getUri?.(uri)).toBe(uri);
    expect(wallet.qrCode?.instructions?.learnMoreUrl).toBe(CAKE_WALLET_DOCS_URL);
    expect(typeof wallet.createConnector).toBe("function");
  });

  it("cannot be created without a project ID (RainbowKit refuses), so it is never listed with a fake one", () => {
    expect(() => cakeWallet({ projectId: "" })).toThrow(/projectId/);
  });
});

describe("MetaMask / browser wallet path", () => {
  it("keeps RainbowKit's own injected wallet, unwrapped, so its chain prompt to 31337 still works", async () => {
    const { injectedWallet } = await import("@rainbow-me/rainbowkit/wallets");
    const withId = buildWalletList(PROJECT_ID);
    const withoutId = buildWalletList(null);
    expect(withId.flatMap((g) => g.wallets)).toContain(injectedWallet);
    expect(withoutId[0].wallets).toEqual([injectedWallet]);
  });
});
