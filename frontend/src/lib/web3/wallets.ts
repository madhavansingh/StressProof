import { getWalletConnectConnector, type Wallet, type WalletList } from "@rainbow-me/rainbowkit";
import { injectedWallet, walletConnectWallet } from "@rainbow-me/rainbowkit/wallets";
import { withWalletConnectGuards } from "./walletConnectGuards";
import { CAKE_WALLET_WALLETCONNECT_CHAIN_IDS, cakeWalletSupportsChain } from "./walletPolicy";
import { ACTIVE_CHAIN_ID as TARGET_CHAIN_ID } from "../contracts";

export const CAKE_WALLET_DOCS_URL = "https://docs.cakewallet.com/features/basic/walletconnect";

// A plain text badge, not Cake Wallet's logo: the brand's own artwork is not bundled here.
const CAKE_WALLET_ICON =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#0b1220"/>' +
      '<text x="32" y="40" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#ffffff" text-anchor="middle">CW</text></svg>'
  );

/**
 * Cake Wallet over WalletConnect: QR code on desktop (scan from Cake Wallet's WalletConnect
 * screen), the standard `wc:` link on mobile. No Cake-specific deep-link scheme is used because
 * none is documented. Signing works only on the chains Cake Wallet supports for WalletConnect.
 */
export function cakeWallet({ projectId }: { projectId: string }): Wallet {
  // Created here so an empty project ID fails at once (RainbowKit throws) instead of at connect time.
  const walletConnectConnector = getWalletConnectConnector({ projectId });
  return {
    id: "cake-wallet",
    name: "Cake Wallet",
    iconUrl: CAKE_WALLET_ICON,
    iconBackground: "#0b1220",
    downloadUrls: { mobile: "https://cakewallet.com", qrCode: "https://cakewallet.com" },
    mobile: { getUri: (uri: string) => uri },
    qrCode: {
      getUri: (uri: string) => uri,
      instructions: {
        learnMoreUrl: CAKE_WALLET_DOCS_URL,
        steps: [
          { step: "install", title: "Open Cake Wallet", description: "Open your Ethereum wallet in Cake Wallet on your phone." },
          { step: "scan", title: "Scan with WalletConnect", description: "In Cake Wallet open WalletConnect, scan this code and approve the connection." },
        ],
      },
    },
    createConnector: (walletDetails) =>
      withWalletConnectGuards(walletConnectConnector(walletDetails), {
        walletName: "Cake Wallet",
        targetChainId: TARGET_CHAIN_ID,
        canSwitchTo: cakeWalletSupportsChain,
        // Without a chain Cake Wallet supports in the proposal it has no account to share and
        // never answers (seen with the real app). These are optional and never app chains.
        extraOptionalChains: CAKE_WALLET_WALLETCONNECT_CHAIN_IDS,
      }),
  };
}

/** RainbowKit's generic WalletConnect entry with the same connection guards (no chain-switch limit). */
function guardedWalletConnectWallet(params: Parameters<typeof walletConnectWallet>[0]): Wallet {
  const wallet = walletConnectWallet(params);
  return {
    ...wallet,
    createConnector: (walletDetails) =>
      withWalletConnectGuards(wallet.createConnector(walletDetails), {
        walletName: "WalletConnect wallet",
        targetChainId: TARGET_CHAIN_ID,
      }),
  };
}

/**
 * Browser wallets are always offered (installed EIP-6963 extensions also appear on their own).
 * WalletConnect wallets, Cake Wallet first, are added only with a real Reown project ID.
 */
export function buildWalletList(projectId: string | null): WalletList {
  if (!projectId) {
    return [{ groupName: "Browser wallet", wallets: [injectedWallet] }];
  }
  return [
    { groupName: "Sponsor", wallets: [cakeWallet] },
    { groupName: "Other wallets", wallets: [injectedWallet, guardedWalletConnectWallet] },
  ];
}
