"use client";

import { CheckCircle2, Clock, ShieldAlert, ArrowRight } from "lucide-react";
import Link from "next/link";

interface AttestationEvent {
  id: string;
  claimId: string;
  title: string;
  amountAtRisk: string;
  type: "settled" | "pending" | "challenge";
  timestamp: string;
  status: "finalized" | "review" | "active";
  rootHash: string;
}

const RECENT_ATTESTATIONS: AttestationEvent[] = [
  {
    id: "att-1",
    claimId: "1",
    title: "CLAIM_#1 // AAVE_V3 -30%",
    amountAtRisk: "$2,000.00",
    type: "settled",
    timestamp: "12M AGO",
    status: "finalized",
    rootHash: "0x7f42...25f0",
  },
  {
    id: "att-2",
    claimId: "2",
    title: "CLAIM_#2 // COMP -50%",
    amountAtRisk: "$5,400.00",
    type: "pending",
    timestamp: "45M AGO",
    status: "active",
    rootHash: "0x9b31...c6e2",
  },
  {
    id: "att-3",
    claimId: "3",
    title: "CLAIM_#3 // SPARK SLIPPAGE",
    amountAtRisk: "$1,120.00",
    type: "challenge",
    timestamp: "2H AGO",
    status: "review",
    rootHash: "0xd421...aa10",
  },
  {
    id: "att-4",
    claimId: "4",
    title: "HEARTBEAT // FORK #19.5M",
    amountAtRisk: "$0.00",
    type: "settled",
    timestamp: "4H AGO",
    status: "finalized",
    rootHash: "0x12bb...ef55",
  },
];

export function RecentAttestationsWidget({ className = "" }: { className?: string }) {
  return (
    <div className={`w-full flex flex-col justify-between space-y-4 font-mono ${className}`}>
      {/* Unified Header */}
      <div className="flex items-center justify-between pb-3 border-b-2 border-border gap-2">
        <div className="min-w-0">
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground block">
            {"// REGISTRY_LOGS"}
          </span>
          <h2 className="text-sm sm:text-base font-bold uppercase tracking-wider text-foreground truncate mt-0.5">
            ATTESTATIONS_STREAM
          </h2>
        </div>
        <div className="shrink-0 flex items-center gap-1.5 px-2 py-0.5 border border-border bg-secondary text-[10px] font-bold text-foreground">
          <span className="h-1.5 w-1.5 bg-[#ea580c] animate-pulse" />
          <span>120S_WINDOW</span>
        </div>
      </div>

      {/* Events List */}
      <div className="space-y-2.5">
        {RECENT_ATTESTATIONS.map((event) => {
          const isSettled = event.type === "settled";
          const isPending = event.type === "pending";

          return (
            <div
              key={event.id}
              className="p-3 border border-border bg-background hover:border-foreground transition-all space-y-2"
            >
              {/* Row 1: Icon + Title + Amount */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <div
                    className={`h-5 w-5 shrink-0 border flex items-center justify-center font-bold text-[10px] ${
                      isSettled
                        ? "border-emerald-500 bg-emerald-950/60 text-emerald-400"
                        : isPending
                        ? "border-amber-500 bg-amber-950/60 text-amber-400"
                        : "border-orange-500 bg-orange-950/60 text-[#ea580c]"
                    }`}
                  >
                    {isSettled ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : isPending ? (
                      <Clock className="h-3 w-3" />
                    ) : (
                      <ShieldAlert className="h-3 w-3" />
                    )}
                  </div>
                  <p className="text-xs font-bold text-foreground uppercase tracking-wider truncate">
                    {event.title}
                  </p>
                </div>

                <div className="text-right shrink-0">
                  <span className="text-xs font-bold text-foreground">
                    {event.amountAtRisk}
                  </span>
                </div>
              </div>

              {/* Row 2: Status Tag + Evidence Hash + Timestamp */}
              <div className="flex items-center justify-between text-[10px] pt-1.5 border-t border-border/40 gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span
                    className={`shrink-0 text-[9px] px-1.5 py-0.2 border uppercase font-bold ${
                      isSettled
                        ? "border-emerald-500 bg-emerald-950/40 text-emerald-400"
                        : isPending
                        ? "border-amber-500 bg-amber-950/40 text-amber-400"
                        : "border-orange-500 bg-orange-950/40 text-[#ea580c]"
                    }`}
                  >
                    {event.status}
                  </span>
                  <span className="text-muted-foreground truncate font-mono">
                    {event.rootHash}
                  </span>
                </div>

                <span className="text-muted-foreground uppercase shrink-0 text-[10px]">
                  {event.timestamp}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer Link */}
      <div className="pt-2">
        <Link
          href="/claims"
          className="flex items-center justify-between p-2.5 border border-dashed border-border bg-muted/10 text-xs font-mono uppercase tracking-wider text-muted-foreground hover:text-foreground hover:border-foreground transition-all"
        >
          <span className="truncate">VIEW_REGISTRY</span>
          <span className="text-[#ea580c] font-bold shrink-0 ml-2 flex items-center gap-1">
            [OPEN_PORTAL <ArrowRight size={12} className="inline" />]
          </span>
        </Link>
      </div>
    </div>
  );
}
