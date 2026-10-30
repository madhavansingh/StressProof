"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { formatEther, type Hex } from "viem";
import { useAccount, usePublicClient, useWriteContract } from "wagmi";
import { AlertTriangle, CheckCircle2, Loader2, Wallet } from "lucide-react";
import { ACTIVE_CHAIN_ID, getContractConfig } from "@/lib/contracts";
import { describeWalletError } from "@/lib/web3/walletPolicy";
import { decodeContractError } from "@/lib/web3/errors";
import { isConfiguredChainId } from "@/lib/web3/wagmi";
import { txPhase, txPhaseLabel } from "@/lib/web3/txStatus";
import { useTxReceipt } from "@/lib/web3/useTxReceipt";
import { withdrawPlan } from "@/lib/web3/withdraw";

const CREDITS_POLL_MS = 4000;

/**
 * The connected account's credited balance on the registry (refunded bonds and rewards) and a
 * Withdraw action. Payouts are pull payments: nothing reaches a wallet until it calls withdraw().
 */
export function CreditsPanel() {
  const { isConnected, address, chainId: walletChainId } = useAccount();
  const config = useMemo(() => getContractConfig(ACTIVE_CHAIN_ID), []);
  const publicClient = usePublicClient({ chainId: ACTIVE_CHAIN_ID });
  const [credits, setCredits] = useState<bigint | undefined>(undefined);
  const [guardError, setGuardError] = useState<string | null>(null);

  const { data: txHash, writeContract, isPending, error: writeError, reset } = useWriteContract();
  const { outcome, isConfirming } = useTxReceipt(txHash, ACTIVE_CHAIN_ID);
  const phase = txPhase({ simulationPassed: false, awaitingSignature: isPending, hash: txHash, receiptStatus: outcome?.status });

  const loadCredits = useCallback(async () => {
    if (!publicClient || !address) {
      setCredits(undefined);
      return;
    }
    try {
      const value = await publicClient.readContract({
        address: config.registry.address,
        abi: config.registry.abi,
        functionName: "credits",
        args: [address],
      });
      setCredits(value as bigint);
    } catch {
      setCredits(undefined);
    }
  }, [publicClient, address, config]);

  useEffect(() => {
    loadCredits();
    const timer = setInterval(loadCredits, CREDITS_POLL_MS);
    return () => clearInterval(timer);
  }, [loadCredits]);

  // A new account or chain starts from a clean slate.
  useEffect(() => {
    reset();
    setGuardError(null);
  }, [address, walletChainId, reset]);

  useEffect(() => {
    if (outcome) loadCredits();
  }, [outcome, loadCredits]);

  async function handleWithdraw() {
    reset();
    const plan = withdrawPlan({
      isConnected,
      address,
      walletChainId,
      targetChainId: ACTIVE_CHAIN_ID,
      registry: config.registry.address,
      credits,
    });
    if (!plan.ok) {
      setGuardError(plan.message);
      return;
    }
    if (!isConfiguredChainId(plan.chainId) || !publicClient || !address) {
      setGuardError(`Nothing sent: chain ${plan.chainId} is not configured in this build.`);
      return;
    }
    try {
      await publicClient.simulateContract({
        account: address as Hex,
        address: config.registry.address,
        abi: config.registry.abi,
        functionName: "withdraw",
      } as never);
    } catch (err: unknown) {
      setGuardError(`Nothing sent: withdraw would revert (${decodeContractError(err).userMessage}).`);
      return;
    }
    setGuardError(null);
    writeContract({
      chainId: plan.chainId,
      address: config.registry.address,
      abi: config.registry.abi,
      functionName: "withdraw",
    });
  }

  if (!isConnected || !address) {
    return (
      <div className="p-3 border border-border bg-card text-xs text-muted-foreground flex items-center gap-2">
        <Wallet className="h-4 w-4 text-[#ea580c] shrink-0" />
        Connect a wallet to see your credited bonds and rewards.
      </div>
    );
  }

  const busy = isPending || isConfirming;
  return (
    <div className="p-3 border-2 border-border bg-card text-xs space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Wallet className="h-4 w-4 text-[#ea580c] shrink-0" />
          <span className="uppercase tracking-wider text-muted-foreground">YOUR_CREDITS:</span>
          <span className="font-bold text-foreground">{credits === undefined ? "…" : `${formatEther(credits)} ETH`}</span>
          <span className="text-muted-foreground">(refunded bonds and rewards; collected with withdraw)</span>
        </div>
        <button
          type="button"
          onClick={handleWithdraw}
          disabled={busy || !credits}
          className="px-3 py-1 border-2 border-foreground bg-foreground text-background font-bold uppercase tracking-wider hover:bg-[#ea580c] hover:border-[#ea580c] hover:text-white transition-all disabled:opacity-50"
        >
          {busy ? "WITHDRAWING..." : "WITHDRAW"}
        </button>
      </div>
      {guardError && (
        <div role="status" className="flex items-center gap-2 text-amber-300">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> {guardError}
        </div>
      )}
      {txHash && (
        <div role="status" className={`flex items-center gap-2 ${phase === "mined-reverted" ? "text-red-300" : "text-emerald-300"}`}>
          {isConfirming ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : phase === "mined-reverted" ? <AlertTriangle className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
          <span>
            {txPhaseLabel(phase)}: <code>{txHash.slice(0, 16)}...</code>
            {phase === "mined-reverted" && outcome?.revertReason && <> — {outcome.revertReason}</>}
          </span>
        </div>
      )}
      {writeError && (
        <div role="status" className="flex items-center gap-2 text-red-300">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> {describeWalletError(writeError).message}
        </div>
      )}
    </div>
  );
}
