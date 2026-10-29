"use client";

import { useEffect, useState, useMemo } from "react";
import { Shield, Lock, AlertCircle, CheckCircle2, PauseCircle, Loader2 } from "lucide-react";
import Link from "next/link";
import { useAccount, usePublicClient } from "wagmi";
import { getContractConfig, ACTIVE_CHAIN_ID } from "@/lib/contracts";
import {
  formatLtvBps,
  formatPaused,
  formatThreshold,
  ltvStatusLabel,
  parseVaultReading,
  vaultConfig,
  type VaultReading,
} from "@/lib/vaultDisplay";

export function VaultDefenseWidget({ className = "" }: { className?: string }) {
  const { chainId } = useAccount();
  const effectiveChainId = ACTIVE_CHAIN_ID; // reads always use the deployment chain, never the wallet's chain
  const config = useMemo(() => getContractConfig(effectiveChainId), [effectiveChainId]);
  const publicClient = usePublicClient({ chainId: effectiveChainId });

  const limits = useMemo(() => vaultConfig(effectiveChainId), [effectiveChainId]);
  // null until a read succeeds, and again after a failed read: never show defaults as live state
  const [vault, setVault] = useState<VaultReading | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let mounted = true;
    async function fetchVaultState() {
      if (!publicClient) return;
      try {
        const [maxLtv, paused, lastApplied] = await Promise.all([
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
        ]);

        if (mounted) {
          setVault(parseVaultReading(maxLtv, paused, lastApplied));
          setLoading(false);
        }
      } catch (err) {
        if (mounted) {
          setVault(null);
          setLoading(false);
        }
      }
    }

    fetchVaultState();
    const interval = setInterval(fetchVaultState, 4000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [publicClient, config]);

  const isLtvTightened =
    vault !== null && limits.defaultMaxLtvBps !== null && vault.maxLtvBps < limits.defaultMaxLtvBps;
  const unavailable = "Vault state unavailable: the RPC read failed";

  const milestones = [
    {
      id: "def-1",
      title: `DYNAMIC LTV REDUCTION (${formatLtvBps(limits.defaultMaxLtvBps)} → ${formatLtvBps(limits.reducedLtvBps)})`,
      subtitle: vault === null
        ? unavailable
        : isLtvTightened
          ? `Triggered on chain by Claim #${vault.lastAppliedClaimId.toString()}`
          : `Armed — tightens on a finalized claim >= ${formatThreshold(limits.ltvThresholdUsd8)}`,
      status: vault === null ? "unknown" : isLtvTightened ? "triggered" : "armed",
      threshold: `THRESHOLD: ${formatThreshold(limits.ltvThresholdUsd8)} BAD DEBT`,
      progress: isLtvTightened ? 100 : 0,
    },
    {
      id: "def-2",
      title: "EMERGENCY BORROW PAUSE CIRCUIT BREAKER",
      subtitle: vault === null
        ? unavailable
        : vault.borrowPaused
          ? "Emergency pause active — all new borrowings halted"
          : `Armed — pauses on a finalized claim >= ${formatThreshold(limits.pauseThresholdUsd8)}`,
      status: vault === null ? "unknown" : vault.borrowPaused ? "triggered" : "armed",
      threshold: `THRESHOLD: ${formatThreshold(limits.pauseThresholdUsd8)} BAD DEBT`,
      progress: vault?.borrowPaused ? 100 : 0,
    },
    {
      id: "def-3",
      title: "OPTIMISTIC DISPUTE WINDOW",
      subtitle: "120-second challenge window with 0.01 ETH bonded stake",
      status: "active",
      threshold: `WINDOW: ${config.challengeWindowSec} SECONDS`,
      progress: 100,
    },
  ];

  return (
    <div className={`w-full flex flex-col justify-between space-y-4 font-mono ${className}`}>
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b-2 border-border">
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-8 w-8 shrink-0 border border-border bg-secondary flex items-center justify-center text-[#ea580c]">
            <Shield className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground block">
              {"// ON_CHAIN_DEFENSE"}
            </span>
            <p className="text-base sm:text-lg md:text-xl font-bold tracking-tight text-foreground mt-0.5 truncate">
              DEMOVAULT_CIRCUIT_BREAKER
            </p>
          </div>
        </div>

        <Link
          href="/vault"
          className="text-xs uppercase font-bold text-muted-foreground hover:text-foreground flex items-center gap-1 group shrink-0"
        >
          <span>MANAGE_CONTROLS</span>
          <Lock className="h-3 w-3 group-hover:text-[#ea580c] transition-colors" />
        </Link>
      </div>

      {/* Defense Parameters Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="p-3 bg-secondary border border-border">
          <span className="text-[10px] text-muted-foreground uppercase block">ACTIVE_MAX_LTV</span>
          <p className="text-xl sm:text-2xl font-bold text-[#ea580c]">
            {formatLtvBps(vault?.maxLtvBps ?? null)}
          </p>
          <span className="text-[10px] text-muted-foreground uppercase">
            {ltvStatusLabel(vault?.maxLtvBps ?? null, limits)}
          </span>
        </div>

        <div className="p-3 bg-secondary border border-border">
          <span className="text-[10px] text-muted-foreground uppercase block">CIRCUIT_STATUS</span>
          <p className="text-xl sm:text-2xl font-bold text-foreground">
            {formatPaused(vault?.borrowPaused ?? null, "HALTED", "OPERATIONAL")}
          </p>
          <span className="text-[10px] text-muted-foreground uppercase">
            {formatPaused(vault?.borrowPaused ?? null, "PAUSE_ACTIVE", "ALL_CHECKS_NORMAL")}
          </span>
        </div>
      </div>

      {/* Milestones List */}
      <div className="border-2 border-border bg-card divide-y-2 divide-border">
        {milestones.map((m) => {
          const isTriggered = m.status === "triggered";

          return (
            <div key={m.id} className="p-3 sm:p-4 hover:bg-secondary/40 transition-colors space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    {isTriggered ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                    ) : (
                      <Lock className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    )}
                    <span className="text-xs sm:text-sm font-bold text-foreground truncate">
                      {m.title}
                    </span>
                  </div>
                  <p className="text-[10px] text-muted-foreground uppercase mt-0.5">
                    {m.subtitle}
                  </p>
                </div>

                <span
                  className={`px-1.5 py-0.5 border text-[9px] font-bold uppercase shrink-0 ${
                    isTriggered
                      ? "border-emerald-500 bg-emerald-950/40 text-emerald-400"
                      : "border-border bg-secondary text-muted-foreground"
                  }`}
                >
                  [{m.status}]
                </span>
              </div>

              <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                <span>{m.threshold}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
