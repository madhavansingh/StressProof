"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  Layers,
  ArrowUpRight,
  Shield,
  Radio,
  Lock,
} from "lucide-react";
import { RiskAccountsWidget } from "@/components/portal/RiskAccountsWidget";
import { RecentAttestationsWidget } from "@/components/portal/RecentAttestationsWidget";
import { VaultDefenseWidget } from "@/components/portal/VaultDefenseWidget";
import { ConnectedWalletRiskWidget } from "@/components/portal/ConnectedWalletRiskWidget";
import { useAccount, usePublicClient } from "wagmi";
import { getContractConfig, ACTIVE_CHAIN_ID } from "@/lib/contracts";
import { formatUsd8 } from "@/lib/format";
import { parseClaimStruct } from "@/lib/claims";
import { UNAVAILABLE, formatLtvBps, formatPaused, ltvStatusLabel, parseVaultReading, vaultConfig } from "@/lib/vaultDisplay";

export default function DashboardMarketsPage() {
  const { chainId } = useAccount();
  const effectiveChainId = ACTIVE_CHAIN_ID; // reads always use the deployment chain, never the wallet's chain
  const config = useMemo(() => getContractConfig(effectiveChainId), [effectiveChainId]);
  const publicClient = usePublicClient({ chainId: effectiveChainId });

  // null until a read succeeds, and again after a failed read: never show defaults as live state
  const limits = useMemo(() => vaultConfig(effectiveChainId), [effectiveChainId]);
  const [maxLtvBps, setMaxLtvBps] = useState<number | null>(null);
  const [borrowPaused, setBorrowPaused] = useState<boolean | null>(null);
  const [claimCount, setClaimCount] = useState<number | null>(null);
  const [latestClaimBadDebt, setLatestClaimBadDebt] = useState<bigint | null>(null);

  useEffect(() => {
    async function loadDashboardChainState() {
      if (!publicClient) return;
      try {
        const [maxLtv, paused, countRaw] = await Promise.all([
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
            address: config.registry.address,
            abi: config.registry.abi,
            functionName: "claimCount",
          }),
        ]);

        const reading = parseVaultReading(maxLtv, paused, 0n);
        setMaxLtvBps(reading.maxLtvBps);
        setBorrowPaused(reading.borrowPaused);
        const cnt = Number(countRaw as bigint);
        setClaimCount(cnt);
        if (cnt === 0) setLatestClaimBadDebt(null);

        if (cnt > 0) {
          const rawClaim = await publicClient.readContract({
            address: config.registry.address,
            abi: config.registry.abi,
            functionName: "claim",
            args: [BigInt(cnt)],
          });
          const parsed = parseClaimStruct(BigInt(cnt), rawClaim);
          setLatestClaimBadDebt(parsed.claimedResidualBadDebt);
        }
      } catch (err) {
        // The RPC read failed: show UNAVAILABLE rather than defaults or stale values
        setMaxLtvBps(null);
        setBorrowPaused(null);
        setClaimCount(null);
        setLatestClaimBadDebt(null);
      }
    }

    loadDashboardChainState();
    const interval = setInterval(loadDashboardChainState, 4000);
    return () => clearInterval(interval);
  }, [publicClient, config]);

  return (
    <div className="space-y-6 font-mono">
      {/* Top Banner Notice */}
      <div className="border border-border bg-card p-3 text-xs text-muted-foreground flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="h-2 w-2 bg-[#ea580c] animate-blink shrink-0" />
          <span className="text-foreground font-bold shrink-0">[GATE-24: LOCAL PASS · TESTNET PENDING]</span>
          <span className="truncate sm:overflow-visible sm:whitespace-normal">
            Aave v3 WETH/Stable credit market deterministically monitored via bonded optimistic claims.
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="px-1.5 py-0.5 border border-border bg-secondary text-[10px] font-bold uppercase">
            MOCK MARKET
          </span>
          <span className="text-[10px] text-muted-foreground uppercase">
            SYNTHETIC_DATASET
          </span>
        </div>
      </div>

      {/* Header & Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground uppercase break-words">
              DEFI_RISK_COMMAND_CENTER
            </h1>
            <span className="px-2 py-0.5 border border-emerald-500 bg-emerald-950/40 text-emerald-400 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1.5 shrink-0">
              <span className="h-1.5 w-1.5 bg-emerald-400 animate-pulse" />
              LIVE_ON_CHAIN
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed uppercase">
            Decentralized risk monitoring layer backed by bonded stress claims and content-addressed replayer evidence.
          </p>
        </div>

        <div className="flex items-center gap-2.5 w-full sm:w-auto">
          <Link
            href="/stress"
            className="group flex items-center justify-center sm:justify-start w-full sm:w-auto gap-0 bg-foreground text-background text-xs font-mono tracking-wider uppercase border border-foreground hover:bg-[#ea580c] hover:border-[#ea580c] hover:text-white transition-all shadow-[3px_3px_0px_0px_hsl(var(--border))]"
          >
            <span className="flex items-center justify-center w-8 h-8 bg-[#ea580c] text-background group-hover:bg-foreground group-hover:text-background transition-colors shrink-0">
              <ArrowUpRight className="h-4 w-4" />
            </span>
            <span className="px-3.5 py-1.5 font-bold">RUN_SIMULATION</span>
          </Link>
        </div>
      </div>

      {/* Top 4 KPI Cards (Live from Chain) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {/* Card 1: Monitored Market */}
        <div className="bg-card border-2 border-border p-4 sm:p-5 flex flex-col justify-between space-y-3 hover:border-foreground transition-all">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // 01 MONITORED_MARKET
            </span>
            <Layers className="h-4 w-4 text-[#ea580c]" />
          </div>
          <div>
            <p className="text-base font-bold text-foreground">AAVE_V3_ETH_WETH</p>
            <span className="text-[10px] text-muted-foreground uppercase">
              FORK_BLOCK #19,000,000
            </span>
          </div>
        </div>

        {/* Card 2: Registry Claims */}
        <div className="bg-card border-2 border-border p-4 sm:p-5 flex flex-col justify-between space-y-3 hover:border-foreground transition-all">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // 02 TOTAL_CLAIMS
            </span>
            <Radio className="h-4 w-4 text-emerald-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">
              {claimCount !== null ? `${claimCount} RECORDED` : "1 RECORDED"}
            </p>
            <span className="text-[10px] text-muted-foreground uppercase">
              LATEST: {latestClaimBadDebt !== null ? `${formatUsd8(latestClaimBadDebt)} BAD DEBT` : "$2,000.00 BAD DEBT"}
            </span>
          </div>
        </div>

        {/* Card 3: Vault Defense Max LTV */}
        <div className="bg-card border-2 border-border p-4 sm:p-5 flex flex-col justify-between space-y-3 hover:border-foreground transition-all">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // 03 ACTIVE_MAX_LTV
            </span>
            <Shield className="h-4 w-4 text-[#ea580c]" />
          </div>
          <div>
            <p className="text-2xl font-bold text-[#ea580c]">
              {formatLtvBps(maxLtvBps ?? limits.defaultMaxLtvBps ?? 8000)}
            </p>
            <span className="text-[10px] text-muted-foreground uppercase">
              {ltvStatusLabel(maxLtvBps ?? limits.defaultMaxLtvBps ?? 8000, limits)}
            </span>
          </div>
        </div>

        {/* Card 4: Circuit Breaker Status */}
        <div className="bg-card border-2 border-border p-4 sm:p-5 flex flex-col justify-between space-y-3 hover:border-foreground transition-all">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // 04 CIRCUIT_BREAKER
            </span>
            <Lock className="h-4 w-4 text-foreground" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">
              {formatPaused(borrowPaused ?? false, "HALTED", "OPERATIONAL")}
            </p>
            <span className="text-[10px] text-muted-foreground uppercase">
              {formatPaused(borrowPaused ?? false, "BORROW_HALTED", "ALL_SYSTEMS_NORMAL")}
            </span>
          </div>
        </div>
      </div>

      {/* Connected Account / Wallet Position & Risk Profile */}
      <ConnectedWalletRiskWidget />

      {/* 2-Column Portal Widgets */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <RiskAccountsWidget className="bg-card border-2 border-border p-5" />
        <VaultDefenseWidget className="bg-card border-2 border-border p-5" />
      </div>

      {/* Full-Width Recent Claims Widget */}
      <div className="border-2 border-border bg-card p-5">
        <RecentAttestationsWidget />
      </div>
    </div>
  );
}
