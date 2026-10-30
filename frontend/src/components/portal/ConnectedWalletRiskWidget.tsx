"use client";

import { useState, useEffect, useMemo } from "react";
import {
  Wallet,
  ShieldCheck,
  AlertTriangle,
  Flame,
  ArrowUpRight,
  TrendingDown,
  Layers,
  Coins,
  Check,
  Copy,
  UserCheck,
} from "lucide-react";
import { useAccount, usePublicClient } from "wagmi";
import { getContractConfig, ACTIVE_CHAIN_ID } from "@/lib/contracts";
import {
  deriveWalletRiskProfile,
  SAMPLE_WALLETS,
  type WalletRiskProfile,
} from "@/lib/walletRisk";

export function ConnectedWalletRiskWidget({ className = "" }: { className?: string }) {
  const { address: connectedAddress, isConnected } = useAccount();
  const effectiveChainId = ACTIVE_CHAIN_ID;
  const config = useMemo(() => getContractConfig(effectiveChainId), [effectiveChainId]);
  const publicClient = usePublicClient({ chainId: effectiveChainId });

  // Selected address (defaults to connected address or fallback)
  const [selectedAddress, setSelectedAddress] = useState<string>(
    connectedAddress || SAMPLE_WALLETS[0].address
  );
  const [copied, setCopied] = useState(false);
  const [onChainDebt, setOnChainDebt] = useState<bigint | null>(null);
  const [onChainCredits, setOnChainCredits] = useState<bigint | null>(null);

  // Sync with connected address changes
  useEffect(() => {
    if (connectedAddress) {
      setSelectedAddress(connectedAddress);
    }
  }, [connectedAddress]);

  // Read live on-chain balances for the selected address if RPC is responsive
  useEffect(() => {
    let mounted = true;
    async function fetchOnChainAccount() {
      if (!publicClient || !selectedAddress || !selectedAddress.startsWith("0x")) return;
      try {
        const [debt, credits] = await Promise.all([
          publicClient
            .readContract({
              address: config.market.address,
              abi: config.market.abi,
              functionName: "debtUsd8",
              args: [selectedAddress as `0x${string}`],
            })
            .catch(() => 0n),
          publicClient
            .readContract({
              address: config.registry.address,
              abi: config.registry.abi,
              functionName: "credits",
              args: [selectedAddress as `0x${string}`],
            })
            .catch(() => 0n),
        ]);

        if (mounted) {
          setOnChainDebt(debt as bigint);
          setOnChainCredits(credits as bigint);
        }
      } catch {
        if (mounted) {
          setOnChainDebt(null);
          setOnChainCredits(null);
        }
      }
    }

    fetchOnChainAccount();
  }, [publicClient, config, selectedAddress]);

  // Derive profile dynamically for the active address
  const profile: WalletRiskProfile = useMemo(() => {
    return deriveWalletRiskProfile(selectedAddress, {
      onChainDebtUsd8: onChainDebt,
      onChainCreditsWei: onChainCredits,
    });
  }, [selectedAddress, onChainDebt, onChainCredits]);

  const copyAddress = () => {
    if (navigator?.clipboard) {
      navigator.clipboard.writeText(profile.address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isConnectedActive = isConnected && connectedAddress?.toLowerCase() === profile.address.toLowerCase();

  // Status visual attributes
  const statusColor =
    profile.healthStatus === "SAFE"
      ? "text-emerald-400 border-emerald-500 bg-emerald-950/40"
      : profile.healthStatus === "MODERATE"
      ? "text-yellow-400 border-yellow-500 bg-yellow-950/40"
      : profile.healthStatus === "AT_RISK"
      ? "text-amber-500 border-amber-500 bg-amber-950/40"
      : "text-rose-500 border-rose-500 bg-rose-950/40 animate-pulse";

  return (
    <div className={`border-2 border-border bg-card p-5 font-mono space-y-5 ${className}`}>
      {/* Top Header Row */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-4 border-b-2 border-border">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground block">
              // 05 CONNECTED_ACCOUNT_RISK_PROFILE
            </span>
            {isConnectedActive ? (
              <span className="px-1.5 py-0.5 border border-emerald-500 bg-emerald-950/40 text-emerald-400 text-[9px] font-bold uppercase flex items-center gap-1">
                <span className="h-1.5 w-1.5 bg-emerald-400 animate-pulse" />
                ACTIVE_CONNECTED_WALLET
              </span>
            ) : (
              <span className="px-1.5 py-0.2 border border-border bg-secondary text-muted-foreground text-[9px] font-bold uppercase">
                INSPECTING_PROFILE
              </span>
            )}
          </div>
          <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground uppercase mt-1 flex flex-wrap items-center gap-2">
            ACCOUNT_POSITION_&_STRESS_EXPOSURE
          </h2>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Deterministic collateral, debt, health factor, and liquidation shock buffer for{" "}
            <span className="text-foreground font-bold">{profile.shortAddress}</span>
          </p>
        </div>

        {/* Status & Role Badges */}
        <div className="flex flex-wrap items-center gap-2">
          <span className={`px-2 py-1 border text-[10px] font-bold uppercase flex items-center gap-1.5 ${profile.roleBadgeClass}`}>
            <UserCheck className="h-3 w-3" />
            {profile.role}
          </span>
          <span className={`px-2 py-1 border text-[10px] font-bold uppercase flex items-center gap-1.5 ${statusColor}`}>
            {profile.healthStatus === "SAFE" ? (
              <ShieldCheck className="h-3 w-3" />
            ) : (
              <AlertTriangle className="h-3 w-3" />
            )}
            HF: {profile.healthFactor} [{profile.healthStatus}]
          </span>
          <button
            onClick={copyAddress}
            className="px-2 py-1 border border-border bg-secondary hover:bg-muted text-[10px] font-bold uppercase flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
            title="Copy Address"
          >
            {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
            {profile.shortAddress}
          </button>
        </div>
      </div>

      {/* Quick Wallet Profile Switcher */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase font-bold">
          <span>// QUICK_WALLET_SWITCHER (INSPECT RISK VARIATIONS ACROSS DIFFERENT ACCOUNTS):</span>
          {connectedAddress && (
            <button
              onClick={() => setSelectedAddress(connectedAddress)}
              className="text-[#ea580c] hover:underline"
            >
              RESET TO MY WALLET
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {connectedAddress && (
            <button
              onClick={() => setSelectedAddress(connectedAddress)}
              className={`px-2.5 py-1 text-[10px] font-bold border transition-all ${
                selectedAddress.toLowerCase() === connectedAddress.toLowerCase()
                  ? "bg-[#ea580c] text-white border-[#ea580c]"
                  : "bg-secondary border-border text-foreground hover:border-foreground"
              }`}
            >
              ★ YOUR_CONNECTED_WALLET ({connectedAddress.slice(0, 6)}...{connectedAddress.slice(-4)})
            </button>
          )}
          {SAMPLE_WALLETS.map((sample) => {
            const isSelected = selectedAddress.toLowerCase() === sample.address.toLowerCase();
            return (
              <button
                key={sample.address}
                onClick={() => setSelectedAddress(sample.address)}
                className={`px-2 py-1 text-[10px] font-bold border transition-all ${
                  isSelected
                    ? "bg-[#ea580c] text-white border-[#ea580c]"
                    : "bg-secondary border-border text-muted-foreground hover:text-foreground hover:border-foreground"
                }`}
                title={sample.description}
              >
                {sample.label} ({sample.address.slice(0, 6)}...{sample.address.slice(-4)})
              </button>
            );
          })}
        </div>
      </div>

      {/* 4 Core Financial Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Metric 1: Collateral Deposited */}
        <div className="border border-border bg-background p-3.5 flex flex-col justify-between space-y-2">
          <div className="flex items-center justify-between text-muted-foreground text-[10px] font-bold uppercase">
            <span>// COLLATERAL_DEPOSITED</span>
            <Coins className="h-3.5 w-3.5 text-foreground" />
          </div>
          <div>
            <p className="text-xl sm:text-2xl font-bold text-foreground">
              ${profile.collateralUsd.toLocaleString()}
            </p>
            <p className="text-[10px] text-muted-foreground uppercase mt-0.5">
              {profile.collateralEth} WETH POOL COLLATERAL
            </p>
          </div>
        </div>

        {/* Metric 2: Outstanding Debt */}
        <div className="border border-border bg-background p-3.5 flex flex-col justify-between space-y-2">
          <div className="flex items-center justify-between text-muted-foreground text-[10px] font-bold uppercase">
            <span>// BORROWED_DEBT</span>
            <ArrowUpRight className="h-3.5 w-3.5 text-[#ea580c]" />
          </div>
          <div>
            <p className="text-xl sm:text-2xl font-bold text-[#ea580c]">
              ${profile.debtUsd.toLocaleString()}
            </p>
            <p className="text-[10px] text-muted-foreground uppercase mt-0.5">
              USDC BORROWED AGAINST WETH
            </p>
          </div>
        </div>

        {/* Metric 3: Account LTV & Gauge */}
        <div className="border border-border bg-background p-3.5 flex flex-col justify-between space-y-2">
          <div className="flex items-center justify-between text-muted-foreground text-[10px] font-bold uppercase">
            <span>// ACCOUNT_LTV</span>
            <Layers className="h-3.5 w-3.5 text-foreground" />
          </div>
          <div>
            <div className="flex items-baseline justify-between">
              <p className="text-xl sm:text-2xl font-bold text-foreground">
                {profile.accountLtvPct.toFixed(2)}%
              </p>
              <span className="text-[10px] text-muted-foreground">
                MAX: {profile.protocolMaxLtvPct.toFixed(2)}%
              </span>
            </div>
            {/* LTV Bar */}
            <div className="w-full bg-secondary h-1.5 mt-2 border border-border overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${
                  profile.accountLtvPct > 70
                    ? "bg-rose-500"
                    : profile.accountLtvPct > 55
                    ? "bg-amber-500"
                    : "bg-emerald-400"
                }`}
                style={{ width: `${Math.min(100, (profile.accountLtvPct / profile.protocolMaxLtvPct) * 100)}%` }}
              />
            </div>
            <p className="text-[9px] text-muted-foreground uppercase mt-1">
              SAFETY BUFFER: +{(profile.protocolMaxLtvPct - profile.accountLtvPct).toFixed(2)}%
            </p>
          </div>
        </div>

        {/* Metric 4: Health Factor & Liquidation Cushion */}
        <div className="border border-border bg-background p-3.5 flex flex-col justify-between space-y-2">
          <div className="flex items-center justify-between text-muted-foreground text-[10px] font-bold uppercase">
            <span>// HEALTH_FACTOR</span>
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
          </div>
          <div>
            <p className={`text-xl sm:text-2xl font-bold ${profile.healthFactor < 1.15 ? "text-rose-500" : "text-emerald-400"}`}>
              {profile.healthFactor.toFixed(2)}
            </p>
            <p className="text-[10px] text-muted-foreground uppercase mt-0.5">
              LIQUIDATION DROP: -{profile.liquidationDropPct}% (${profile.liquidationPriceEth}/ETH)
            </p>
          </div>
        </div>
      </div>

      {/* Bottom Summary Strip: Stress Impact & Protocol Participation */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 text-[11px] border-t border-border">
        {/* Stress Shock Projected Loss */}
        <div className="bg-secondary/40 border border-border p-3 flex items-start gap-2.5">
          <TrendingDown className="h-4 w-4 text-[#ea580c] shrink-0 mt-0.5" />
          <div>
            <span className="font-bold uppercase text-foreground block">
              STRESS_SCENARIO EXPOSURE (-30% SHOCK)
            </span>
            <span className="text-muted-foreground text-[10px] block mt-0.5">
              {profile.stressLossUsd > 0
                ? `Projected bad debt: $${profile.stressLossUsd.toLocaleString()} at $2,100/ETH shock.`
                : "Solvent — collateral covers debt obligations even under a 30% flash crash."}
            </span>
          </div>
        </div>

        {/* Protocol Staking & Bonds */}
        <div className="bg-secondary/40 border border-border p-3 flex items-start gap-2.5">
          <Flame className="h-4 w-4 text-purple-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-bold uppercase text-foreground block">
              BONDED ATTESTATION STAKE
            </span>
            <span className="text-muted-foreground text-[10px] block mt-0.5">
              {profile.bondedEth > 0
                ? `${profile.bondedEth} ETH in escrow across ${profile.claimsCount} active claims.`
                : "No active optimistic claim bonds committed by this account."}
            </span>
          </div>
        </div>

        {/* Unclaimed Settlement Credits */}
        <div className="bg-secondary/40 border border-border p-3 flex items-start gap-2.5">
          <Coins className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-bold uppercase text-foreground block">
              WITHDRAWABLE SETTLEMENT CREDITS
            </span>
            <span className="text-muted-foreground text-[10px] block mt-0.5">
              {profile.withdrawableCreditsEth > 0
                ? `${profile.withdrawableCreditsEth} ETH available for withdrawal in StressRegistry.`
                : "No settlement credits pending withdrawal for this address."}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
