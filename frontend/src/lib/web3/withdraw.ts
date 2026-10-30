import { checkWriteReadiness } from "./walletPolicy";

export interface WithdrawPlanInput {
  isConnected: boolean;
  address: string | undefined;
  walletChainId: number | undefined;
  targetChainId: number;
  registry: string | undefined;
  /** The connected account's credits(address) on the registry; undefined until read. */
  credits: bigint | undefined;
}

export type WithdrawPlan = { ok: true; chainId: number } | { ok: false; message: string };

/**
 * Whether the connected account may call withdraw(): the usual write checks (connected, on the
 * deployment chain, registry deployed) plus a positive credited balance. Bonds and rewards are pull
 * payments, so this is the only way they leave the registry.
 */
export function withdrawPlan(input: WithdrawPlanInput): WithdrawPlan {
  const ready = checkWriteReadiness({
    isConnected: input.isConnected,
    address: input.address,
    walletChainId: input.walletChainId,
    targetChainId: input.targetChainId,
    contractAddress: input.registry,
  });
  if (!ready.ok) return { ok: false, message: ready.message };
  if (input.credits === undefined) return { ok: false, message: "Nothing sent: the credited balance has not loaded yet." };
  if (input.credits <= 0n) return { ok: false, message: "Nothing to withdraw: this account has no credited balance." };
  return { ok: true, chainId: ready.chainId };
}
