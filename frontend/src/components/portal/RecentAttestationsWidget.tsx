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
    title: "CLAIM_#1 // AAVE_V3 -30% SHOCK",
    amountAtRisk: "$2,000.00",
    type: "settled",
    timestamp: "12M AGO",
    status: "finalized",
    rootHash: "0x7f42...25f0",
  },
  {
    id: "att-2",
    claimId: "2",
    title: "CLAIM_#2 // COMPOUND -50% CRASH",
    amountAtRisk: "$5,400.00",
    type: "pending",
    timestamp: "45M AGO",
    status: "active",
    rootHash: "0x9b31...c6e2",
  },
  {
    id: "att-3",
    claimId: "3",
    title: "CLAIM_#3 // SPARK HIGH SLIPPAGE",
    amountAtRisk: "$1,120.00",
    type: "challenge",
    timestamp: "2H AGO",
    status: "review",
    rootHash: "0xd421...aa10",
  },
  {
    id: "att-4",
    claimId: "4",
    title: "HEARTBEAT // FORK #19,500,000",
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
      {/* Top Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b-2 border-border">
        <div className="min-w-0">
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground block">
            {"// REGISTRY_LOGS"}
          </span>
          <p className="text-base sm:text-lg font-bold tracking-tight text-foreground mt-0.5 truncate">
            RECENT_ATTESTATIONS
          </p>
        </div>
        <div className="shrink-0 flex items-center gap-1.5 px-2 py-0.5 border border-border bg-secondary text-[10px] font-bold text-foreground">
          <span>[OPTIMISTIC_WINDOW]</span>
        </div>
      </div>

      {/* Events List */}
      <div className="space-y-2">
        {RECENT_ATTESTATIONS.map((event) => {
          const isSettled = event.type === "settled";
          const isPending = event.type === "pending";

          return (
            <div
              key={event.id}
              className="flex items-center justify-between p-3 border border-border bg-background hover:border-foreground transition-all"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`h-8 w-8 border flex items-center justify-center font-bold text-xs ${
                    isSettled
                      ? "border-emerald-500 bg-emerald-950/60 text-emerald-400"
                      : isPending
                      ? "border-amber-500 bg-amber-950/60 text-amber-400"
                      : "border-orange-500 bg-orange-950/60 text-[#ea580c]"
                  }`}
                >
                  {isSettled ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : isPending ? (
                    <Clock className="h-4 w-4" />
                  ) : (
                    <ShieldAlert className="h-4 w-4" />
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-xs font-bold text-foreground uppercase tracking-wider">
                      {event.title}
                    </p>
                    <span
                      className={`text-[9px] px-1 border uppercase font-bold ${
                        isSettled
                          ? "border-emerald-500 text-emerald-400"
                          : isPending
                          ? "border-amber-500 text-amber-400"
                          : "border-orange-500 text-[#ea580c]"
                      }`}
                    >
                      [{event.status}]
                    </span>
                  </div>
                  <p className="text-[10px] text-muted-foreground uppercase">
                    EVIDENCE: {event.rootHash} &bull; {event.timestamp}
                  </p>
                </div>
              </div>

              <div className="text-right">
                <p className="text-xs font-bold text-foreground">{event.amountAtRisk}</p>
                <p className="text-[10px] text-muted-foreground uppercase font-bold">
                  BOND: 0.01 ETH
                </p>
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
          <span>VIEW_BONDED_REGISTRY &rarr;</span>
          <span className="text-[#ea580c] font-bold">[CHALLENGE_PORTAL]</span>
        </Link>
      </div>
    </div>
  );
}
