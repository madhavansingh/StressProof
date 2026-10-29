import { connectorsForWallets } from "@rainbow-me/rainbowkit";
import { baseSepolia, hardhat } from "wagmi/chains";
import { createConfig, http } from "wagmi";
import { buildWalletList } from "@/lib/web3/wallets";
import { walletConnectProjectId } from "@/lib/web3/walletPolicy";

export const TARGET_CHAIN_ID = Number(process.env.NEXT_PUBLIC_CHAIN_ID) || 31337;

export const localRpcUrl =
  process.env.NEXT_PUBLIC_LOCAL_RPC_URL || "http://127.0.0.1:8546";
export const baseSepoliaRpcUrl =
  process.env.NEXT_PUBLIC_BASE_SEPOLIA_RPC_URL || "https://sepolia.base.org";

// Local Anvil chain definition using port 8546 as the default RPC endpoint
export const localAnvilChain = {
  ...hardhat,
  id: 31337,
  name: "Anvil Local",
  rpcUrls: {
    default: { http: [localRpcUrl] },
    public: { http: [localRpcUrl] },
  },
} as const;

/** null when NEXT_PUBLIC_WC_PROJECT_ID is unset or a placeholder: WalletConnect wallets are then hidden. */
export const WALLETCONNECT_PROJECT_ID = walletConnectProjectId(process.env.NEXT_PUBLIC_WC_PROJECT_ID);

const connectors = connectorsForWallets(buildWalletList(WALLETCONNECT_PROJECT_ID), {
  appName: "StressProof",
  // Only WalletConnect wallets use the project ID, and they are not listed without a real one.
  projectId: WALLETCONNECT_PROJECT_ID ?? "walletconnect-disabled",
});

export const config = createConfig({
  connectors,
  chains: TARGET_CHAIN_ID === 84532 ? [baseSepolia, localAnvilChain] : [localAnvilChain, baseSepolia],
  transports: {
    [localAnvilChain.id]: http(localRpcUrl),
    [baseSepolia.id]: http(baseSepoliaRpcUrl),
  },
  ssr: true,
});

export type ConfiguredChainId = (typeof config.chains)[number]["id"];

export function isConfiguredChainId(id: number): id is ConfiguredChainId {
  return config.chains.some((chain) => chain.id === id);
}
