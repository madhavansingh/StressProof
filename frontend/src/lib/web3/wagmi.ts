import { getDefaultConfig } from "@rainbow-me/rainbowkit";
import { baseSepolia, hardhat } from "wagmi/chains";

export const config = getDefaultConfig({
  appName: "StressProof",
  projectId: process.env.NEXT_PUBLIC_WC_PROJECT_ID || "demo_project_id",
  chains: [hardhat, baseSepolia],
  ssr: true,
});
