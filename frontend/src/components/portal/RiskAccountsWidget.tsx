"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, ArrowRight, Layers, Shield } from "lucide-react";
import Link from "next/link";
import { fetchDatasets } from "@/lib/api/client";

interface MonitoredMarket {
  marketId: string;
  name: string;
  asset: string;
  dataClass: string;
  forkBlock: number;
  syntheticAccounts: number;
  realAccounts: number;
}

export function RiskAccountsWidget({ className = "" }: { className?: string }) {
  const [datasets, setDatasets] = useState<any[]>([]);

  useEffect(() => {
    fetchDatasets()
      .then((data) => {
        if (Array.isArray(data)) {
          setDatasets(data);
        }
      })
      .catch(() => {});
  }, []);

  const monitoredMarkets: MonitoredMarket[] = datasets.length > 0
    ? datasets.map((d) => ({
        marketId: "aave-v3-eth-weth-stable",
        name: `Aave v3 Fork (#${d.forkBlock})`,
        asset: "WETH / Stablecoins",
        dataClass: d.dataClass || "SYNTHETIC",
        forkBlock: d.forkBlock || 19000000,
        syntheticAccounts: d.counts?.synthetic || 0,
        realAccounts: d.counts?.real || 0,
      }))
    : [
        {
          marketId: "aave-v3-eth-weth-stable",
          name: "Aave v3 Core Fork (#19000000)",
          asset: "WETH / Stablecoins",
          dataClass: "SYNTHETIC",
          forkBlock: 19000000,
          syntheticAccounts: 6,
          realAccounts: 0,
        },
      ];

  return (
    <div className={`w-full flex flex-col justify-between space-y-4 font-mono ${className}`}>
      {/* Top Total TVL Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b-2 border-border">
        <div>
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground block">
            {"// MONITORED_MARKETS"}
          </span>
          <p className="text-base sm:text-lg md:text-xl font-bold tracking-tight text-foreground mt-0.5">
            LENDING_MARKET_TOPOLOGY
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 border border-border bg-secondary text-[10px] font-bold uppercase">
            MOCK MARKET
          </span>
        </div>
      </div>

      {/* Markets List */}
      <div className="border-2 border-border bg-card divide-y-2 divide-border">
        {monitoredMarkets.map((m) => (
          <div
            key={m.marketId}
            className="p-3 sm:p-4 hover:bg-secondary/40 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3"
          >
            <div className="flex items-start sm:items-center gap-3 min-w-0">
              <div className="h-8 w-8 shrink-0 border border-border bg-background flex items-center justify-center text-[#ea580c]">
                <Layers className="h-4 w-4" />
              </div>

              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs sm:text-sm font-bold text-foreground">
                    {m.name}
                  </span>
                  <span className="px-1.5 py-0.2 border border-border bg-secondary text-[9px] font-bold uppercase text-muted-foreground">
                    [{m.dataClass}]
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2 mt-1 text-[10px] text-muted-foreground">
                  <span>PAIR: {m.asset}</span>
                  <span>&bull;</span>
                  <span>
                    ACCOUNTS: {m.syntheticAccounts} SYNTHETIC / {m.realAccounts} REAL
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0">
              <Link
                href="/stress"
                className="px-2.5 py-1 border border-border bg-background hover:border-foreground text-[10px] font-bold text-foreground uppercase flex items-center gap-1 transition-all"
              >
                <span>SIMULATE</span>
                <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
