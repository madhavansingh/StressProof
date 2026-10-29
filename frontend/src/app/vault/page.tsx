"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useAccount, usePublicClient, useWriteContract, useWaitForTransactionReceipt } from "wagmi";
import { getContractConfig, ACTIVE_CHAIN_ID } from "@/lib/contracts";
import { decodeContractError } from "@/lib/web3/errors";
import { formatUsd8, formatAddress } from "@/lib/format";
import {
  Shield,
  Lock,
  AlertTriangle,
  CheckCircle2,
  Zap,
  RefreshCw,
  Loader2,
  Terminal,
} from "lucide-react";

export default function VaultPage() {
  const { isConnected, address: userAddress, chainId: currentChainId } = useAccount();
  const effectiveChainId = currentChainId || ACTIVE_CHAIN_ID;
  const config = useMemo(() => getContractConfig(effectiveChainId), [effectiveChainId]);
  const publicClient = usePublicClient({ chainId: effectiveChainId });

  // On-chain DemoVault state
  const [maxLtvBps, setMaxLtvBps] = useState<number>(8000);
  const [borrowPaused, setBorrowPaused] = useState<boolean>(false);
  const [lastAppliedClaimId, setLastAppliedClaimId] = useState<bigint>(0n);
  const [vaultOwner, setVaultOwner] = useState<`0x${string}` | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [rpcError, setRpcError] = useState<string | null>(null);

  // Borrow simulator fields: $10,000 collateral, $7,000 borrow (70% LTV)
  const [collateralInput, setCollateralInput] = useState<string>("10000");
  const [borrowAmountInput, setBorrowAmountInput] = useState<string>("7000");
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [borrowStatus, setBorrowStatus] = useState<{
    success: boolean;
    message: string;
    errorName?: string;
  } | null>(null);

  // Reset controls transaction
  const {
    data: resetTxHash,
    writeContract: writeReset,
    isPending: isResetPending,
    error: resetError,
    reset: clearReset,
  } = useWriteContract();

  const { isLoading: isResetConfirming, isSuccess: isResetConfirmed } =
    useWaitForTransactionReceipt({ hash: resetTxHash });

  // Fetch real vault state from chain
  const loadVaultData = useCallback(async () => {
    if (!publicClient) return;
    try {
      setRpcError(null);
      const [maxLtv, paused, lastApplied, owner] = await Promise.all([
        publicClient.readContract({
          address: config.vault.address,
          abi: config.vault.abi,
          functionName: "maxLtvBps",
        }),
        publicClient.readContract({
          address: config.vault.address,
          abi: config.vault.abi,
          functionName: "borrowPaused",
        }),
        publicClient.readContract({
          address: config.vault.address,
          abi: config.vault.abi,
          functionName: "lastAppliedClaimId",
        }),
        publicClient.readContract({
          address: config.vault.address,
          abi: config.vault.abi,
          functionName: "owner",
        }),
      ]);

      setMaxLtvBps(Number(maxLtv as bigint | number));
      setBorrowPaused(Boolean(paused));
      setLastAppliedClaimId(BigInt(lastApplied as bigint | number));
      setVaultOwner(owner as `0x${string}`);
      setIsLoading(false);
    } catch (err: any) {
      console.error("Failed to load DemoVault data from RPC:", err);
      setRpcError(err?.message || "Failed to query RPC for DemoVault parameters.");
      setIsLoading(false);
    }
  }, [publicClient, config]);

  useEffect(() => {
    loadVaultData();
    const interval = setInterval(loadVaultData, 4000);
    return () => clearInterval(interval);
  }, [loadVaultData]);

  useEffect(() => {
    if (isResetConfirmed) {
      loadVaultData();
    }
  }, [isResetConfirmed, loadVaultData]);

  // Try real borrow simulation via eth_call
  async function handleTryBorrow() {
    if (!publicClient) return;
    setIsSimulating(true);
    setBorrowStatus(null);

    try {
      // 8 decimals: $10,000 = 1000000000000n, $7,000 = 700000000000n
      const colUsd8 = BigInt(Math.floor(Number(collateralInput || "0"))) * 100000000n;
      const amtUsd8 = BigInt(Math.floor(Number(borrowAmountInput || "0"))) * 100000000n;

      await publicClient.simulateContract({
        address: config.market.address,
        abi: config.market.abi,
        functionName: "borrow",
        args: [colUsd8, amtUsd8],
      });

      const reqLtvBps =
        colUsd8 > 0n ? Number((amtUsd8 * 10000n) / colUsd8) : 0;

      setBorrowStatus({
        success: true,
        message: `SUCCESS: Borrowed $${Number(borrowAmountInput).toLocaleString()} against $${Number(
          collateralInput
        ).toLocaleString()} at ${(reqLtvBps / 100).toFixed(2)}% LTV.`,
      });
    } catch (err: any) {
      const decoded = decodeContractError(err);
      setBorrowStatus({
        success: false,
        errorName: decoded.errorName,
        message: `REVERT: ${decoded.userMessage}`,
      });
    } finally {
      setIsSimulating(false);
    }
  }

  function handleResetControls() {
    clearReset();
    writeReset({
      address: config.vault.address,
      abi: config.vault.abi,
      functionName: "resetControls",
    });
  }

  const isOwner = userAddress && vaultOwner && userAddress.toLowerCase() === vaultOwner.toLowerCase();

  return (
    <div className="max-w-5xl space-y-6 font-mono">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground uppercase break-words">
              DEMOVAULT_RISK_CONTROLS
            </h1>
            <span className="px-2 py-0.5 border border-border bg-secondary text-foreground text-[10px] font-bold uppercase tracking-wider shrink-0">
              DEMOVAULT.SOL
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed uppercase">
            Automated on-chain circuit breakers dynamically tightened when bonded bad debt claims finalize.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => loadVaultData()}
            title="Refresh parameters"
            className="p-2 border border-border bg-card hover:border-foreground text-muted-foreground hover:text-foreground transition-all"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin text-[#ea580c]" : ""}`} />
          </button>
          <button
            disabled={isResetPending || isResetConfirming || (!isOwner && !borrowPaused && maxLtvBps === 8000)}
            onClick={handleResetControls}
            className="w-full sm:w-auto px-4 py-2 text-xs font-bold uppercase tracking-wider border-2 border-foreground bg-foreground text-background hover:bg-[#ea580c] hover:border-[#ea580c] hover:text-white transition-all shrink-0 disabled:opacity-50"
          >
            {isResetPending || isResetConfirming ? "RESETTING..." : "RESET_VAULT_CONTROLS"}
          </button>
        </div>
      </div>

      {resetTxHash && (
        <div className="p-3 border-2 border-emerald-500 bg-emerald-950/40 text-emerald-300 text-xs flex items-center justify-between">
          <span>CONTROLS_RESET_TX: {resetTxHash}</span>
          <span className="font-bold text-[10px] uppercase">
            {isResetConfirming ? "CONFIRMING..." : "CONFIRMED"}
          </span>
        </div>
      )}

      {resetError && (
        <div className="p-3 border-2 border-red-500 bg-red-950/40 text-red-300 text-xs">
          ERROR: {decodeContractError(resetError).userMessage}
        </div>
      )}

      {rpcError && (
        <div className="p-4 border-2 border-amber-500 bg-amber-950/40 text-amber-200 text-xs space-y-1">
          <div className="flex items-center gap-2 font-bold uppercase text-amber-400">
            <AlertTriangle className="h-4 w-4" />
            RPC_CONNECTIVITY_NOTICE
          </div>
          <p className="text-[11px] uppercase">
            Failed to query DemoVault at <code>{config.vault.address}</code>. Check local Anvil on port 8546.
          </p>
        </div>
      )}

      {/* Top Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card border-2 border-border p-5 flex flex-col justify-between space-y-3">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // CURRENT_MAX_LTV
            </span>
            <Shield className="h-4 w-4 text-[#ea580c]" />
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              <p className="text-3xl font-bold text-[#ea580c]">{(maxLtvBps / 100).toFixed(2)}%</p>
              <span className="text-xs text-muted-foreground line-through">80.00%</span>
            </div>
            <span className="text-[10px] text-muted-foreground uppercase">
              {lastAppliedClaimId > 0n
                ? `DYNAMICALLY TIGHTENED BY CLAIM #${lastAppliedClaimId.toString()}`
                : "BASELINE UNALTERED PARAMETER"}
            </span>
          </div>
        </div>

        <div className="bg-card border-2 border-border p-5 flex flex-col justify-between space-y-3">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // CIRCUIT_BREAKER_STATUS
            </span>
            <Lock className="h-4 w-4 text-[#ea580c]" />
          </div>
          <div>
            <p className="text-3xl font-bold text-foreground">
              {borrowPaused ? "HALTED" : "OPERATIONAL"}
            </p>
            <span className="text-[10px] text-muted-foreground uppercase">
              PAUSE_THRESHOLD: $4,000.00 BAD DEBT
            </span>
          </div>
        </div>
      </div>

      {/* Borrow Simulator Section */}
      <div className="bg-card border-2 border-border p-6 space-y-6">
        <div className="flex items-center justify-between border-b-2 border-border pb-3">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-[#ea580c]" />
            <h3 className="text-xs font-bold uppercase tracking-widest text-foreground">
              TEST_BORROW_SIMULATOR (MOCKLENDINGMARKET.SOL)
            </h3>
          </div>
          <span className="text-[10px] text-muted-foreground uppercase">
            MARKET: {formatAddress(config.market.address)}
          </span>
        </div>

        <p className="text-xs text-muted-foreground uppercase leading-relaxed">
          Simulates an on-chain borrow request via <code>eth_call</code> against <code>MockLendingMarket</code>. If requested LTV exceeds the vault's active limit, the transaction reverts with custom error <code>LtvTooHigh</code>.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div>
              <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
                COLLATERAL (USD)
              </label>
              <input
                type="number"
                value={collateralInput}
                onChange={(e) => setCollateralInput(e.target.value)}
                className="w-full bg-background border-2 border-border p-2.5 text-xs text-foreground font-mono focus:border-foreground outline-none"
              />
            </div>

            <div>
              <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
                BORROW_AMOUNT (USD)
              </label>
              <input
                type="number"
                value={borrowAmountInput}
                onChange={(e) => setBorrowAmountInput(e.target.value)}
                className="w-full bg-background border-2 border-border p-2.5 text-xs text-foreground font-mono focus:border-foreground outline-none"
              />
            </div>
          </div>

          <div className="border border-border p-4 bg-muted/20 flex flex-col justify-between">
            <div className="space-y-2">
              <span className="text-[10px] text-muted-foreground uppercase tracking-widest block">
                SIMULATION_PARAMETERS
              </span>
              <div className="text-xs space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">REQUESTED_LTV:</span>
                  <span className="font-bold text-foreground">
                    {Number(collateralInput) > 0
                      ? ((Number(borrowAmountInput) / Number(collateralInput)) * 100).toFixed(2)
                      : "0.00"}
                    %
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">MAX_ALLOWED_LTV:</span>
                  <span className="font-bold text-[#ea580c]">{(maxLtvBps / 100).toFixed(2)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">CIRCUIT_BREAKER:</span>
                  <span className="font-bold text-foreground">
                    {borrowPaused ? "PAUSED" : "ACTIVE"}
                  </span>
                </div>
              </div>
            </div>

            <button
              disabled={isSimulating}
              onClick={handleTryBorrow}
              className="w-full mt-4 py-2.5 bg-[#ea580c] text-white border-2 border-[#ea580c] text-xs font-bold uppercase tracking-wider hover:bg-foreground hover:text-background hover:border-foreground transition-all disabled:opacity-50"
            >
              {isSimulating ? "SIMULATING_ETH_CALL..." : "EXECUTE_BORROW_SIMULATION"}
            </button>
          </div>
        </div>

        {borrowStatus && (
          <div
            className={`p-4 border-2 text-xs font-mono ${
              borrowStatus.success
                ? "border-emerald-500 bg-emerald-950/40 text-emerald-300"
                : "border-rose-500 bg-rose-950/40 text-rose-300"
            }`}
          >
            {borrowStatus.message}
          </div>
        )}
      </div>
    </div>
  );
}
