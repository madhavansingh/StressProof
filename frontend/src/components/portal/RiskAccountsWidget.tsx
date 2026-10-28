"use client";

import { AlertTriangle, CheckCircle2, ArrowRight } from "lucide-react";
import Link from "next/link";

interface RiskAccount {
  id: string;
  name: string;
  protocol: string;
  tvl: string;
  healthFactor: string;
  riskStatus: "healthy" | "warning" | "critical";
  monitoredDebt: string;
}

const RISK_ACCOUNTS: RiskAccount[] = [
  {
    id: "aave-v3-eth",
    name: "Aave v3 Ethereum Core Fork",
    protocol: "WETH / Stablecoins",
    tvl: "$15,230,800",
    healthFactor: "1.42 HF",
    riskStatus: "healthy",
    monitoredDebt: "$6.2M Debt",
  },
  {
    id: "compound-v3-weth",
    name: "Compound v3 Comet Market",
    protocol: "WETH / USDC Pool",
    tvl: "$8,459,450",
    healthFactor: "1.08 HF",
    riskStatus: "warning",
    monitoredDebt: "$4.1M Debt",
  },
  {
    id: "spark-steth-pool",
    name: "Spark Protocol High LTV",
    protocol: "wstETH / DAI Core",
    tvl: "$4,850,000",
    healthFactor: "1.65 HF",
    riskStatus: "healthy",
    monitoredDebt: "$1.8M Debt",
  },
  {
    id: "morpho-blue-weth",
    name: "Morpho Blue Isolated Vault",
    protocol: "WETH / PYUSD LLTV 91.5%",
    tvl: "$2,850,000",
    healthFactor: "1.02 HF",
    riskStatus: "critical",
    monitoredDebt: "$1.2M Debt",
  },
];

export function RiskAccountsWidget({ className = "" }: { className?: string }) {
  return (
    <div className={`w-full flex flex-col justify-between space-y-4 font-mono ${className}`}>
      {/* Top Total TVL Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b-2 border-border">
        <div>
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground block">
            {"// MONITORED_EXPOSURE"}
          </span>
          <p className="text-lg sm:text-xl md:text-2xl font-bold tracking-tight text-foreground mt-0.5">
            $31,390,250
          </p>
        </div>
        <div className="shrink-0 flex items-center gap-1.5 px-2.5 py-1 border border-border bg-secondary text-[10px] sm:text-[11px] font-bold text-foreground">
          <span>[4_ACTIVE_POOLS]</span>
        </div>
      </div>

      {/* Account Items List */}
      <div className="space-y-2">
        {RISK_ACCOUNTS.map((account) => {
          const isCritical = account.riskStatus === "critical";
          const isWarning = account.riskStatus === "warning";
          return (
            <div
              key={account.id}
              className="flex items-center justify-between p-2.5 sm:p-3 border border-border bg-background hover:border-foreground transition-all gap-2"
            >
              <div className="flex items-center gap-2.5 sm:gap-3 min-w-0 flex-1">
                <div
                  className={`h-8 w-8 shrink-0 border flex items-center justify-center font-bold text-xs ${
                    isCritical
                      ? "border-rose-500 bg-rose-950/60 text-rose-400"
                      : isWarning
                      ? "border-amber-500 bg-amber-950/60 text-amber-400"
                      : "border-border bg-secondary text-foreground"
                  }`}
                >
                  {isCritical || isWarning ? (
                    <AlertTriangle className="h-4 w-4" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4" />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1 sm:gap-2">
                    <p className="text-xs font-bold text-foreground uppercase tracking-wider truncate max-w-[130px] sm:max-w-xs md:max-w-none">
                      {account.name}
                    </p>
                    <span
                      className={`text-[9px] px-1 border uppercase font-bold shrink-0 ${
                        isCritical
                          ? "border-rose-500 text-rose-400"
                          : isWarning
                          ? "border-amber-500 text-amber-400"
                          : "border-emerald-500 text-emerald-400"
                      }`}
                    >
                      {account.riskStatus}
                    </span>
                  </div>
                  <p className="text-[10px] text-muted-foreground uppercase truncate">{account.protocol}</p>
                </div>
              </div>

              <div className="text-right shrink-0">
                <p className="text-xs font-bold text-foreground">{account.tvl}</p>
                <p
                  className={`text-[10px] font-bold ${
                    isCritical ? "text-rose-400" : isWarning ? "text-amber-400" : "text-muted-foreground"
                  }`}
                >
                  {account.healthFactor}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Widget Footer */}
      <div className="pt-2">
        <Link
          href="/stress"
          className="flex flex-wrap items-center justify-between gap-2 p-2.5 border border-dashed border-border bg-muted/10 text-xs font-mono uppercase tracking-wider text-muted-foreground hover:text-foreground hover:border-foreground transition-all"
        >
          <span>SIMULATE_PRICE_SHOCK &rarr;</span>
          <span className="text-[#ea580c] font-bold">[STRESS_RUNNER]</span>
        </Link>
      </div>
    </div>
  );
}
