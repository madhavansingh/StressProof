import IStressRegistryAbi from "../abi/IStressRegistry.json";
import DemoVaultAbi from "../abi/DemoVault.json";
import MockLendingMarketAbi from "../abi/MockLendingMarket.json";

import deployment31337 from "../../../deployments/31337.json";
import deployment84532 from "../../../deployments/84532.json";

export { IStressRegistryAbi, DemoVaultAbi, MockLendingMarketAbi };

export interface DeploymentConfig {
  chainId: number;
  registry: `0x${string}`;
  vault: `0x${string}`;
  market: `0x${string}`;
  marketId: `0x${string}`;
  marketIdString?: string;
  bondWei: string;
  challengeWindowSec: number;
  resolutionWindowSec: number;
  registryDeployBlock: number;
  resolver?: `0x${string}`;
  pauseThresholdUsd8?: string;
  ltvThresholdUsd8?: string;
  reducedLtvBps?: number;
  defaultMaxLtvBps?: number;
  gitCommit?: string;
}

export const DEPLOYMENTS: Record<number, DeploymentConfig> = {
  31337: deployment31337 as unknown as DeploymentConfig,
  84532: deployment84532 as unknown as DeploymentConfig,
};

export const ACTIVE_CHAIN_ID = Number(process.env.NEXT_PUBLIC_CHAIN_ID) || 31337;

export function getContractConfig(chainId: number = ACTIVE_CHAIN_ID) {
  const deployment = DEPLOYMENTS[chainId] || DEPLOYMENTS[31337];
  return {
    chainId: deployment.chainId,
    registry: {
      address: deployment.registry,
      abi: IStressRegistryAbi,
    },
    vault: {
      address: deployment.vault,
      abi: DemoVaultAbi,
    },
    market: {
      address: deployment.market,
      abi: MockLendingMarketAbi,
    },
    marketId: deployment.marketId,
    bondWei: BigInt(deployment.bondWei || "10000000000000000"),
    challengeWindowSec: deployment.challengeWindowSec,
    resolutionWindowSec: deployment.resolutionWindowSec,
    registryDeployBlock: BigInt(deployment.registryDeployBlock || 0),
  };
}
