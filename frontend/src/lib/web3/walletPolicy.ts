import { BaseError, isAddress, zeroAddress } from "viem";

/**
 * EVM chains on which Cake Wallet supports WalletConnect, per its official documentation
 * (https://docs.cakewallet.com/features/basic/walletconnect.md): Ethereum, Polygon, Base,
 * Arbitrum, BNB Smart Chain and Robinhood Chain. Local Anvil (31337) and Base Sepolia (84532)
 * are not among them, so Cake Wallet cannot sign StressProof transactions on those chains.
 */
export const CAKE_WALLET_WALLETCONNECT_CHAIN_IDS: readonly number[] = [1, 137, 8453, 42161, 56, 4663];

export function cakeWalletSupportsChain(chainId: number): boolean {
  return CAKE_WALLET_WALLETCONNECT_CHAIN_IDS.includes(chainId);
}

const PLACEHOLDER_PROJECT_IDS = new Set(["", "demo_project_id", "your_project_id", "YOUR_PROJECT_ID"]);

/**
 * A Reown (WalletConnect) project ID from the environment, or null when it is missing or a
 * placeholder. WalletConnect wallets, including Cake Wallet, are offered only when it is real.
 */
export function walletConnectProjectId(raw: string | undefined): string | null {
  const value = (raw ?? "").trim();
  return PLACEHOLDER_PROJECT_IDS.has(value) ? null : value;
}

export type WriteReadiness =
  | { ok: true; chainId: number }
  | { ok: false; kind: "disconnected" | "wrong-network" | "no-deployment"; message: string };

export interface WriteReadinessInput {
  isConnected: boolean;
  address: string | undefined;
  walletChainId: number | undefined;
  targetChainId: number;
  contractAddress: string | undefined;
}

/**
 * Checked before every wallet write: a connected account, a real deployment on the app's chain,
 * and the wallet on exactly that chain. Writes then pass `chainId: targetChainId`, so the wallet
 * can never be asked to send on another network.
 */
export function checkWriteReadiness(input: WriteReadinessInput): WriteReadiness {
  const { isConnected, address, walletChainId, targetChainId, contractAddress } = input;
  if (!isConnected || !address) {
    return { ok: false, kind: "disconnected", message: "Nothing sent: connect a wallet first." };
  }
  if (!contractAddress || !isAddress(contractAddress) || contractAddress.toLowerCase() === zeroAddress) {
    return {
      ok: false,
      kind: "no-deployment",
      message: `Nothing sent: no StressProof contracts are recorded for chain ${targetChainId}.`,
    };
  }
  if (walletChainId !== targetChainId) {
    // Wallet-specific advice (for example a wallet that cannot add this chain) comes from the
    // wrong-network banner, which acts on what a switch request actually returned.
    return {
      ok: false,
      kind: "wrong-network",
      message: `Nothing sent: the wallet is on chain ${walletChainId ?? "unknown"}, StressProof is on chain ${targetChainId}. Switch the wallet to chain ${targetChainId} to send transactions.`,
    };
  }
  return { ok: true, chainId: targetChainId };
}

export type WalletErrorKind = "rejected" | "wrong-network" | "disconnected" | "other";

const NAMES_BY_KIND: Record<Exclude<WalletErrorKind, "other">, string[]> = {
  rejected: ["UserRejectedRequestError"],
  "wrong-network": ["ChainMismatchError", "ConnectorChainMismatchError", "ChainNotConfiguredError", "SwitchChainNotSupportedError"],
  disconnected: ["ConnectorNotConnectedError", "ConnectorAccountNotFoundError", "ConnectorNotFoundError"],
};

const MESSAGES: Record<WalletErrorKind, string> = {
  rejected: "Request rejected in the wallet. Nothing was sent.",
  "wrong-network": "The wallet is on a different network than StressProof. Nothing was sent.",
  disconnected: "No wallet is connected. Nothing was sent.",
  other: "",
};

function errorChain(err: unknown): unknown[] {
  const chain: unknown[] = [];
  let current: unknown = err;
  for (let depth = 0; current && depth < 10; depth++) {
    chain.push(current);
    current = (current as { cause?: unknown }).cause;
  }
  return chain;
}

/** Maps wallet / wagmi / viem errors to a plain sentence; never reports success. */
export function describeWalletError(err: unknown): { kind: WalletErrorKind; message: string } {
  for (const e of errorChain(err)) {
    const name = (e as { name?: string }).name ?? "";
    const code = (e as { code?: number }).code;
    if (NAMES_BY_KIND.rejected.includes(name) || code === 4001) return { kind: "rejected", message: MESSAGES.rejected };
    if (NAMES_BY_KIND["wrong-network"].includes(name)) return { kind: "wrong-network", message: MESSAGES["wrong-network"] };
    if (NAMES_BY_KIND.disconnected.includes(name)) return { kind: "disconnected", message: MESSAGES.disconnected };
  }
  const message =
    err instanceof BaseError ? err.shortMessage : err instanceof Error ? err.message : "Unknown wallet error";
  return { kind: "other", message: message.slice(0, 200) };
}
