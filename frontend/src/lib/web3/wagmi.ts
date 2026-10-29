import { getDefaultConfig } from "@rainbow-me/rainbowkit";
import { baseSepolia, hardhat } from "wagmi/chains";
import { http } from "wagmi";

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

export const config = getDefaultConfig({
  appName: "StressProof",
  projectId: process.env.NEXT_PUBLIC_WC_PROJECT_ID || "demo_project_id",
  chains: TARGET_CHAIN_ID === 84532 ? [baseSepolia, localAnvilChain] : [localAnvilChain, baseSepolia],
  transports: {
    [localAnvilChain.id]: http(localRpcUrl),
    [baseSepolia.id]: http(baseSepoliaRpcUrl),
  },
  ssr: true,
});
