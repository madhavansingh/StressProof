"use client";

import Link from "next/link";
import {
  Layers,
  ArrowUpRight,
  TrendingDown,
  Shield,
  Radio,
  FileCheck2,
  Lock,
} from "lucide-react";
import { RiskAccountsWidget } from "@/components/portal/RiskAccountsWidget";
import { RecentAttestationsWidget } from "@/components/portal/RecentAttestationsWidget";
import { VaultDefenseWidget } from "@/components/portal/VaultDefenseWidget";

export default function DashboardMarketsPage() {
  const market = {
    id: "aave-v3-eth-weth-stable",
    name: "Aave v3 Ethereum Core Fork",
    pair: "WETH / Stablecoins",
    dataClass: "REAL",
    forkBlock: 19500000,
    wethPrice: 300000000000, // $3,000.00
    totalTvl: "$31.4M",
    monitoredBorrowers: 5,
    vaultState: {
      borrowPaused: false,
      defaultMaxLtvBps: 8000,
      currentMaxLtvBps: 5000,
      pauseThresholdUsd8: "400000000002",
      ltvThresholdUsd8: "100000000000",
    },
    latestClaim: {
      id: "1",
      status: "Finalized",
      claimedResidualBadDebt: "200000000001", // $2,000.00
    },
  };

  return (
    <div className="space-y-6 font-mono">
      {/* Top Banner Notice */}
      <div className="border border-border bg-card p-3 text-xs text-muted-foreground flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 bg-[#ea580c] animate-blink" />
          <span className="text-foreground font-bold">[FORK_VERIFIED]</span>
          <span>
            Ethereum Mainnet block #{market.forkBlock} replayed deterministically via static replayer.
          </span>
        </div>
        <span className="hidden sm:inline text-[10px] text-muted-foreground uppercase">
          PROTOCOL_REV: 0x82a9
        </span>
      </div>

      {/* Header & Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground uppercase">
              DEFI_RISK_COMMAND_CENTER
            </h1>
            <span className="px-2 py-0.5 border border-emerald-500 bg-emerald-950/40 text-emerald-400 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 bg-emerald-400 animate-pulse" />
              LIVE_FORK
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed uppercase">
            Decentralized risk monitoring layer backed by bonded stress claims and content-addressed replayer evidence.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Link
            href="/stress"
            className="group flex items-center gap-0 bg-foreground text-background text-xs font-mono tracking-wider uppercase border border-foreground hover:bg-[#ea580c] hover:border-[#ea580c] hover:text-white transition-all shadow-[3px_3px_0px_0px_hsl(var(--border))]"
          >
            <span className="flex items-center justify-center w-8 h-8 bg-[#ea580c] text-background group-hover:bg-foreground group-hover:text-background transition-colors">
              <ArrowUpRight className="h-4 w-4" />
            </span>
            <span className="px-3.5 py-1.5 font-bold">RUN_SIMULATION</span>
          </Link>
        </div>
      </div>

      {/* Top 4 KPI Cards (Brutalist Style) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Monitored TVL */}
        <div className="bg-card border-2 border-border p-5 flex flex-col justify-between space-y-3 hover:border-foreground transition-all">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // 01 MONITORED_TVL
            </span>
            <Layers className="h-4 w-4 text-[#ea580c]" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">{market.totalTvl}</p>
            <span className="text-[10px] text-muted-foreground uppercase">
              FORK_BLOCK #{market.forkBlock}
            </span>
          </div>
        </div>

        {/* Card 2: WETH Base Price */}
        <div className="bg-card border-2 border-border p-5 flex flex-col justify-between space-y-3 hover:border-foreground transition-all">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // 02 WETH_ORACLE
            </span>
            <Radio className="h-4 w-4 text-[#ea580c]" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">$3,000.00</p>
            <span className="text-[10px] text-emerald-400 uppercase font-bold flex items-center gap-1">
              <span className="h-1.5 w-1.5 bg-emerald-400 animate-pulse" />
              FEED_SYNCED
            </span>
          </div>
        </div>

        {/* Card 3: Claimed Bad Debt */}
        <div className="bg-card border-2 border-border p-5 flex flex-col justify-between space-y-3 hover:border-foreground transition-all">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // 03 RESIDUAL_BAD_DEBT
            </span>
            <FileCheck2 className="h-4 w-4 text-[#ea580c]" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">$2,000.00</p>
            <span className="text-[10px] text-emerald-400 uppercase font-bold">
              [CLAIM_#1_FINALIZED]
            </span>
          </div>
        </div>

        {/* Card 4: Circuit Breaker Max LTV */}
        <div className="bg-card border-2 border-border p-5 flex flex-col justify-between space-y-3 hover:border-foreground transition-all">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // 04 VAULT_DEFENSE_LTV
            </span>
            <Lock className="h-4 w-4 text-[#ea580c]" />
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              <p className="text-2xl font-bold text-[#ea580c]">50.00%</p>
              <span className="text-xs text-muted-foreground line-through">80.00%</span>
            </div>
            <span className="text-[10px] text-[#ea580c] uppercase font-bold">
              [CIRCUIT_BREAKER_TRIPPED]
            </span>
          </div>
        </div>
      </div>

      {/* Main 2-Column Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Protocol Risk Accounts (2 Cols) */}
        <div className="lg:col-span-2 bg-card border-2 border-border p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase tracking-wider text-foreground">
              BORROWER_RISK_ACCOUNTS &amp; WATERFALL
            </h2>
            <span className="text-[10px] text-muted-foreground uppercase">AAVE_V3_FORK</span>
          </div>
          <RiskAccountsWidget />
        </div>

        {/* Right Column: Recent Attestations & Registry */}
        <div className="bg-card border-2 border-border p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase tracking-wider text-foreground">
              ATTESTATIONS_STREAM
            </h2>
            <span className="text-[10px] text-muted-foreground uppercase">120S_WINDOW</span>
          </div>
          <RecentAttestationsWidget />
        </div>
      </div>

      {/* Bottom Section: Vault Defense Automation */}
      <div className="bg-card border-2 border-border p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold uppercase tracking-wider text-foreground">
            DEMOVAULT_CIRCUIT_BREAKER_AUTOMATION
          </h2>
          <span className="text-[10px] text-muted-foreground uppercase">DEMOVAULT.SOL</span>
        </div>
        <VaultDefenseWidget />
      </div>
    </div>
  );
}
