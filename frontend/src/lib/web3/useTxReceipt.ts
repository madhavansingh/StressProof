"use client";

import { useQuery } from "@tanstack/react-query";
import { usePublicClient } from "wagmi";
import type { Hex } from "viem";
import type { ConfiguredChainId } from "./wagmi";
import { fetchReceiptOutcome, type ReceiptClient, type ReceiptOutcome } from "./txReceipt";

interface TxReceiptState {
  /** How the mined transaction ended; undefined until it is mined. */
  outcome: ReceiptOutcome | undefined;
  /** A hash was submitted and its receipt is still being waited for. */
  isConfirming: boolean;
  /** Waiting failed for a reason other than a revert (for example the RPC went away). */
  error: Error | null;
}

/**
 * Receipt of a submitted transaction on the deployment chain, reverted receipts included
 * (see fetchReceiptOutcome for why wagmi's useWaitForTransactionReceipt is not used).
 */
export function useTxReceipt(hash: Hex | undefined, chainId: number): TxReceiptState {
  const publicClient = usePublicClient({ chainId: chainId as ConfiguredChainId });
  const query = useQuery({
    queryKey: ["stressproof-tx-receipt", chainId, hash],
    enabled: Boolean(hash && publicClient),
    queryFn: () => fetchReceiptOutcome(publicClient as unknown as ReceiptClient, hash as Hex),
    staleTime: Infinity,
    retry: 2,
  });
  return {
    outcome: query.data,
    isConfirming: Boolean(hash) && query.isLoading,
    error: query.error ?? null,
  };
}
