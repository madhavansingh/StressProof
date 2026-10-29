"use client";

import Link from "next/link";
import { useEffect, useState, useCallback, useMemo } from "react";
import { useAccount, usePublicClient, useWriteContract, useWaitForTransactionReceipt } from "wagmi";
import { getContractConfig, ACTIVE_CHAIN_ID } from "@/lib/contracts";
import { parseClaimStruct, OnChainClaim, calculateBlockTimeCountdown } from "@/lib/claims";
import { formatUsd8, formatAddress } from "@/lib/format";
import { formatEther, keccak256, toHex } from "viem";
import {
  ShieldAlert,
  Clock,
  ArrowRight,
  X,
  AlertTriangle,
  RefreshCw,
  ExternalLink,
  CheckCircle2,
  Loader2,
} from "lucide-react";

export default function ClaimsPage() {
  const { isConnected, chainId: currentChainId } = useAccount();
  const effectiveChainId = currentChainId || ACTIVE_CHAIN_ID;
  const config = useMemo(() => getContractConfig(effectiveChainId), [effectiveChainId]);
  const publicClient = usePublicClient({ chainId: effectiveChainId });

  const [claims, setClaims] = useState<OnChainClaim[]>([]);
  const [blockTimestamp, setBlockTimestamp] = useState<number>(0);
  const [fetchTimestamp, setFetchTimestamp] = useState<number>(0);
  const [tick, setTick] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [rpcError, setRpcError] = useState<string | null>(null);

  // Active dispute / challenge modal state
  const [activeModalClaim, setActiveModalClaim] = useState<OnChainClaim | null>(null);
  const [challengeReason, setChallengeReason] = useState<"WRONG_RESULT" | "EVIDENCE_INVALID">("WRONG_RESULT");
  const [counterDebtInput, setCounterDebtInput] = useState<string>("200000000001");
  const [reportURIInput, setReportURIInput] = useState<string>("http://127.0.0.1:8000/replay-reports/report_sample.json");

  // Write operations
  const { data: writeTxHash, writeContract, isPending: isWritePending, error: writeError, reset: resetWrite } = useWriteContract();
  const { isLoading: isTxConfirming, isSuccess: isTxConfirmed } = useWaitForTransactionReceipt({ hash: writeTxHash });

  // Main data loader from contract
  const loadClaims = useCallback(async () => {
    if (!publicClient) return;
    try {
      setRpcError(null);
      const [block, countRaw] = await Promise.all([
        publicClient.getBlock(),
        publicClient.readContract({
          address: config.registry.address,
          abi: config.registry.abi,
          functionName: "claimCount",
        }),
      ]);

      const count = Number(countRaw as bigint);
      const bTime = Number(block.timestamp);
      setBlockTimestamp(bTime);
      setFetchTimestamp(Date.now());

      if (count === 0) {
        setClaims([]);
        setIsLoading(false);
        return;
      }

      // Batch read claims 1..count
      const claimPromises = [];
      for (let i = 1; i <= count; i++) {
        claimPromises.push(
          publicClient.readContract({
            address: config.registry.address,
            abi: config.registry.abi,
            functionName: "claim",
            args: [BigInt(i)],
          })
        );
      }

      const results = await Promise.all(claimPromises);
      const parsed = results.map((raw, idx) => parseClaimStruct(BigInt(idx + 1), raw));
      setClaims(parsed);
      setIsLoading(false);
    } catch (err: any) {
      console.error("Failed to load claims from RPC:", err);
      setRpcError(err?.message || "Failed to query RPC for claims.");
      setIsLoading(false);
    }
  }, [publicClient, config]);

  // Initial fetch and 4-second polling interval
  useEffect(() => {
    loadClaims();
    const pollInterval = setInterval(loadClaims, 4000);
    return () => clearInterval(pollInterval);
  }, [loadClaims]);

  // 1-second tick for local elapsed countdown accuracy
  useEffect(() => {
    const tickInterval = setInterval(() => {
      setTick((t) => t + 1);
    }, 1000);
    return () => clearInterval(tickInterval);
  }, []);

  // When tx confirms, reload claims immediately
  useEffect(() => {
    if (isTxConfirmed) {
      loadClaims();
    }
  }, [isTxConfirmed, loadClaims]);

  // Compute local elapsed seconds since block timestamp was fetched
  const localElapsed = fetchTimestamp > 0 ? Math.floor((Date.now() - fetchTimestamp) / 1000) : 0;

  function getStatusBadge(status: string) {
    switch (status) {
      case "Pending":
        return "border-amber-500 bg-amber-950/60 text-amber-400";
      case "Challenged":
        return "border-[#ea580c] bg-orange-950/60 text-[#ea580c]";
      case "Finalized":
        return "border-emerald-500 bg-emerald-950/60 text-emerald-400";
      case "Rejected":
        return "border-rose-500 bg-rose-950/60 text-rose-400";
      case "Expired":
        return "border-border bg-secondary text-muted-foreground";
      default:
        return "border-border bg-card text-muted-foreground";
    }
  }

  function handleFinalize(id: bigint) {
    resetWrite();
    writeContract({
      address: config.registry.address,
      abi: config.registry.abi,
      functionName: "finalize",
      args: [id],
    });
  }

  function handleExpire(id: bigint) {
    resetWrite();
    writeContract({
      address: config.registry.address,
      abi: config.registry.abi,
      functionName: "expireUnresolved",
      args: [id],
    });
  }

  function submitChallenge() {
    if (!activeModalClaim) return;
    resetWrite();

    const reasonCode = challengeReason === "WRONG_RESULT" ? 1 : 2;
    const counterDebt = challengeReason === "WRONG_RESULT" ? BigInt(counterDebtInput || "0") : 0n;
    const reportHash = keccak256(toHex(reportURIInput || "report_bytes"));

    writeContract({
      address: config.registry.address,
      abi: config.registry.abi,
      functionName: "challenge",
      args: [activeModalClaim.id, reasonCode, counterDebt, reportURIInput, reportHash],
      value: config.bondWei,
    });

    setActiveModalClaim(null);
  }

  return (
    <div className="space-y-6 font-mono">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground uppercase break-words">
              BONDED_CLAIMS_REGISTRY
            </h1>
            <span className="px-2 py-0.5 border border-border bg-secondary text-foreground text-[10px] font-bold uppercase tracking-wider shrink-0">
              ISTRESSREGISTRY.SOL
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed uppercase">
            On-chain risk claims verified by deterministic Wasm replayer. Each claim requires a {formatEther(config.bondWei)} ETH bond.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => loadClaims()}
            title="Refresh registry"
            className="p-2 border border-border bg-card hover:border-foreground text-muted-foreground hover:text-foreground transition-all"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin text-[#ea580c]" : ""}`} />
          </button>
          <Link
            href="/stress"
            className="group flex items-center justify-center sm:justify-start w-full sm:w-auto gap-0 bg-foreground text-background text-xs font-mono tracking-wider uppercase border border-foreground hover:bg-[#ea580c] hover:border-[#ea580c] hover:text-white transition-all shadow-[3px_3px_0px_0px_hsl(var(--border))]"
          >
            <span className="flex items-center justify-center w-8 h-8 bg-[#ea580c] text-background group-hover:bg-foreground group-hover:text-background transition-colors shrink-0">
              <ArrowRight className="h-4 w-4" />
            </span>
            <span className="px-3.5 py-1.5 font-bold">POST_NEW_CLAIM</span>
          </Link>
        </div>
      </div>

      {/* Transaction Status Notice */}
      {writeTxHash && (
        <div className="p-3 border-2 border-emerald-500 bg-emerald-950/40 text-emerald-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            {isTxConfirming ? (
              <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
            ) : (
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            )}
            <span>
              TRANSACTION_{isTxConfirming ? "PENDING" : "CONFIRMED"}: <code>{writeTxHash.slice(0, 16)}...</code>
            </span>
          </div>
          <button onClick={() => resetWrite()} className="text-emerald-400 hover:text-white uppercase font-bold text-[10px]">
            [DISMISS]
          </button>
        </div>
      )}

      {writeError && (
        <div className="p-3 border-2 border-red-500 bg-red-950/40 text-red-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
            <span className="break-all">{writeError.message.slice(0, 160)}...</span>
          </div>
          <button onClick={() => resetWrite()} className="text-red-400 hover:text-white uppercase font-bold text-[10px]">
            [DISMISS]
          </button>
        </div>
      )}

      {/* RPC Failure Notice */}
      {rpcError && (
        <div className="p-4 border-2 border-amber-500 bg-amber-950/40 text-amber-200 text-xs space-y-1">
          <div className="flex items-center gap-2 font-bold uppercase text-amber-400">
            <AlertTriangle className="h-4 w-4" />
            RPC_CONNECTIVITY_WARNING
          </div>
          <p className="text-[11px] text-amber-300 uppercase leading-relaxed">
            Unable to connect to registry at <code>{config.registry.address}</code> on Chain ID {effectiveChainId}. Ensure local Anvil is running on port 8546.
          </p>
        </div>
      )}

      {/* Claims Table / List */}
      <div className="bg-card border-2 border-border">
        <div className="px-5 py-3 border-b-2 border-border bg-muted/20 flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-bold uppercase tracking-widest text-foreground">
            // REGISTRY_LEDGER ({claims.length}_RECORDS)
          </span>
          <div className="flex items-center gap-4 text-[10px] text-muted-foreground uppercase">
            <span>REGISTRY: {formatAddress(config.registry.address)}</span>
            <span>CHALLENGE_WINDOW: {config.challengeWindowSec}S</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          {isLoading && claims.length === 0 ? (
            <div className="p-12 text-center text-xs text-muted-foreground uppercase space-y-2">
              <Loader2 className="h-6 w-6 animate-spin mx-auto text-[#ea580c]" />
              <p>QUERYING CONTRACT LEDGER VIA RPC...</p>
            </div>
          ) : claims.length === 0 ? (
            <div className="p-12 text-center text-xs text-muted-foreground uppercase space-y-2">
              <ShieldAlert className="h-8 w-8 mx-auto text-muted-foreground" />
              <p className="text-foreground font-bold">NO CLAIMS FOUND IN REGISTRY</p>
              <p className="text-[10px]">Execute a simulation or run the e2e test suite to post bonded claims.</p>
            </div>
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="border-b-2 border-border bg-secondary/50 text-muted-foreground uppercase tracking-wider text-[10px]">
                <tr>
                  <th className="p-4">CLAIM_ID</th>
                  <th className="p-4">STATUS</th>
                  <th className="p-4">MARKET_ID</th>
                  <th className="p-4">CLAIMED_BAD_DEBT</th>
                  <th className="p-4">BOND</th>
                  <th className="p-4">WINDOW_TIMER</th>
                  <th className="p-4">ATTESTER</th>
                  <th className="p-4 text-right">ACTIONS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {claims.map((c) => {
                  const countdown = calculateBlockTimeCountdown(
                    c.challengeDeadline,
                    blockTimestamp,
                    localElapsed
                  );
                  const isChallengeable = c.stateName === "Pending" && !countdown.isExpired;
                  const canFinalize = c.stateName === "Pending" && countdown.isExpired;

                  return (
                    <tr key={c.id.toString()} className="hover:bg-muted/10 transition-colors">
                      <td className="p-4 font-bold text-foreground">#{c.id.toString()}</td>
                      <td className="p-4">
                        <span className={`px-2 py-0.5 border text-[10px] font-bold uppercase tracking-wider ${getStatusBadge(c.stateName)}`}>
                          [{c.stateName}]
                        </span>
                      </td>
                      <td className="p-4 text-muted-foreground font-mono text-[11px]" title={c.marketId}>
                        {c.marketId.slice(0, 10)}...{c.marketId.slice(-6)}
                      </td>
                      <td className="p-4 font-bold text-foreground">
                        {formatUsd8(c.claimedResidualBadDebt)}
                      </td>
                      <td className="p-4 text-foreground">{formatEther(config.bondWei)} ETH</td>
                      <td className="p-4">
                        {c.stateName === "Pending" ? (
                          <span className={`font-bold flex items-center gap-1 ${countdown.isExpired ? "text-emerald-400" : "text-[#ea580c]"}`}>
                            <Clock className="h-3.5 w-3.5" />
                            {countdown.text}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">&mdash;</span>
                        )}
                      </td>
                      <td className="p-4 text-muted-foreground font-mono">
                        {formatAddress(c.attester)}
                      </td>
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Link
                            href={`/claims/${c.id.toString()}`}
                            className="px-2.5 py-1 border border-border text-[11px] font-bold text-foreground hover:bg-secondary uppercase"
                          >
                            DETAIL
                          </Link>
                          {isChallengeable && (
                            <button
                              onClick={() => {
                                setActiveModalClaim(c);
                                setCounterDebtInput(c.claimedResidualBadDebt.toString());
                              }}
                              className="px-2.5 py-1 border border-[#ea580c] bg-[#ea580c] text-background text-[11px] font-bold uppercase hover:bg-foreground hover:border-foreground transition-all"
                            >
                              CHALLENGE
                            </button>
                          )}
                          {canFinalize && (
                            <button
                              disabled={isWritePending}
                              onClick={() => handleFinalize(c.id)}
                              className="px-2.5 py-1 border border-emerald-500 bg-emerald-950/60 text-emerald-300 text-[11px] font-bold uppercase hover:bg-emerald-900 transition-all disabled:opacity-50"
                            >
                              FINALIZE
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Challenge Modal Dialog */}
      {activeModalClaim && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-card border-2 border-foreground p-6 space-y-4 font-mono shadow-[8px_8px_0px_0px_#ea580c]">
            <div className="flex items-center justify-between border-b-2 border-border pb-3">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 bg-[#ea580c] animate-blink" />
                <h3 className="text-sm font-bold uppercase tracking-wider text-foreground">
                  CHALLENGE_CLAIM_#{activeModalClaim.id.toString()}
                </h3>
              </div>
              <button
                onClick={() => setActiveModalClaim(null)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-xs text-muted-foreground uppercase leading-relaxed">
              Submit a counter-bond ({formatEther(config.bondWei)} ETH). If the deterministic replayer reveals the claim is invalid or incorrect, the attester's bond is slashed and credited to you.
            </p>

            <div className="space-y-3">
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
                  DISPUTE_REASON
                </label>
                <select
                  value={challengeReason}
                  onChange={(e: any) => setChallengeReason(e.target.value)}
                  className="w-full bg-background border-2 border-border p-2 text-xs text-foreground font-mono focus:border-foreground outline-none"
                >
                  <option value="WRONG_RESULT">WRONG_RESULT (Bad debt mismatch)</option>
                  <option value="EVIDENCE_INVALID">EVIDENCE_INVALID (Corrupted or malformed hash)</option>
                </select>
              </div>

              {challengeReason === "WRONG_RESULT" && (
                <div>
                  <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
                    ASSERTED_COUNTER_DEBT (USD8)
                  </label>
                  <input
                    type="text"
                    value={counterDebtInput}
                    onChange={(e) => setCounterDebtInput(e.target.value)}
                    className="w-full bg-background border-2 border-border p-2 text-xs text-foreground font-mono focus:border-foreground outline-none"
                  />
                  <span className="text-[10px] text-muted-foreground mt-0.5 block">
                    Format: {formatUsd8(counterDebtInput || "0")}
                  </span>
                </div>
              )}

              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
                  REPLAYER_REPORT_URI
                </label>
                <input
                  type="text"
                  value={reportURIInput}
                  onChange={(e) => setReportURIInput(e.target.value)}
                  className="w-full bg-background border-2 border-border p-2 text-xs text-foreground font-mono focus:border-foreground outline-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t-2 border-border">
              <button
                onClick={() => setActiveModalClaim(null)}
                className="px-4 py-2 border border-border text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground"
              >
                CANCEL
              </button>
              <button
                disabled={isWritePending}
                onClick={submitChallenge}
                className="px-5 py-2 bg-[#ea580c] text-white border-2 border-[#ea580c] text-xs font-bold uppercase tracking-wider hover:bg-foreground hover:text-background hover:border-foreground transition-all disabled:opacity-50"
              >
                {isWritePending ? "TRANSACTING..." : `SUBMIT_CHALLENGE (${formatEther(config.bondWei)} ETH)`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
