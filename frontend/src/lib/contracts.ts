import IStressRegistryAbi from "@/abi/IStressRegistry.json";
import DemoVaultAbi from "@/abi/DemoVault.json";
import MockLendingMarketAbi from "@/abi/MockLendingMarket.json";

export { IStressRegistryAbi, DemoVaultAbi, MockLendingMarketAbi };

export const DEPLOYED_ADDRESSES = {
  // Chain 31337 (Local Anvil)
  31337: {
    registry: "0x5FbDB2315678afecb367f032d93F642f64180aa3" as `0x${string}`,
    vault: "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512" as `0x${string}`,
    market: "0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0" as `0x${string}`,
    marketId: "0x40d51381e4b3e8a71bbbf288e285817d4567c9c0f99b2eb8c15682fa08d3c7c2" as `0x${string}`,
  },
  // Chain 84532 (Base Sepolia)
  84532: {
    registry: "0x0000000000000000000000000000000000000000" as `0x${string}`,
    vault: "0x0000000000000000000000000000000000000000" as `0x${string}`,
    market: "0x0000000000000000000000000000000000000000" as `0x${string}`,
    marketId: "0x40d51381e4b3e8a71bbbf288e285817d4567c9c0f99b2eb8c15682fa08d3c7c2" as `0x${string}`,
  },
} as const;

export function getContractConfig(chainId: number) {
  const addresses = (DEPLOYED_ADDRESSES as Record<number, any>)[chainId] || DEPLOYED_ADDRESSES[31337];
  return {
    registry: {
      address: addresses.registry,
      abi: IStressRegistryAbi,
    },
    vault: {
      address: addresses.vault,
      abi: DemoVaultAbi,
    },
    market: {
      address: addresses.market,
      abi: MockLendingMarketAbi,
    },
    marketId: addresses.marketId,
  };
}

