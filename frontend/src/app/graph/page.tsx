"use client";

import { Activity, Layers, ArrowUpRight } from "lucide-react";
import Link from "next/link";

export default function GraphPage() {
  return (
    <div className="space-y-6 font-mono">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground uppercase break-words">
              TIGERGRAPH_EXPOSURE_GRAPH
            </h1>
            <span className="px-2 py-0.5 border border-border bg-secondary text-foreground text-[10px] font-bold uppercase tracking-wider shrink-0">
              GRAPH_V2
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed uppercase">
            Multilateral borrower collateral network and liquidation cascade graph.
          </p>
        </div>
      </div>

      <div className="bg-card border-2 border-border p-8 flex flex-col items-center justify-center min-h-[380px] text-center space-y-4">
        <div className="h-12 w-12 border-2 border-[#ea580c] bg-[#ea580c]/10 flex items-center justify-center text-[#ea580c]">
          <Activity className="h-6 w-6" />
        </div>
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-foreground">
            TIGERGRAPH_2D_FORCE_GRAPH_REPLAY
          </h3>
          <p className="text-xs text-muted-foreground mt-1 max-w-md uppercase">
            Graph topology model connecting 5 monitored borrower nodes to Aave v3 pool liquidity reserves.
          </p>
        </div>
        <Link
          href="/stress"
          className="px-4 py-2 bg-foreground text-background text-xs font-bold uppercase tracking-wider hover:bg-[#ea580c] hover:text-white transition-all border border-foreground"
        >
          SIMULATE_GRAPH_CASCADE &rarr;
        </Link>
      </div>
    </div>
  );
}
