"use client";

import { Shield, Lock, AlertCircle, CheckCircle2, PauseCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

interface DefenseMilestone {
  id: string;
  title: string;
  subtitle: string;
  status: "active" | "armed" | "triggered";
  threshold: string;
  progress: number;
}

const DEFENSE_MILESTONES: DefenseMilestone[] = [
  {
    id: "def-1",
    title: "DYNAMIC LTV REDUCTION (80% → 50%)",
    subtitle: "Triggered automatically by Claim #1 residual bad debt",
    status: "triggered",
    threshold: "THRESHOLD: $1,000 BAD DEBT",
    progress: 100,
  },
  {
    id: "def-2",
    title: "EMERGENCY BORROW PAUSE CIRCUIT BREAKER",
    subtitle: "Halts all new borrowings across monitored markets",
    status: "armed",
    threshold: "THRESHOLD: $4,000 BAD DEBT",
    progress: 50,
  },
  {
    id: "def-3",
    title: "DISPUTE CHALLENGE WINDOW (OPTIMISTIC)",
    subtitle: "Counter-bond verification and replayer cross-check",
    status: "active",
    threshold: "WINDOW: 120 SECONDS (DEMO)",
    progress: 85,
  },
];

export function VaultDefenseWidget({ className = "" }: { className?: string }) {
  return (
    <div className={`w-full flex flex-col justify-between space-y-4 font-mono ${className}`}>
      {/* Top Header */}
      <div className="flex items-center justify-between pb-3 border-b-2 border-border">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 border border-border bg-secondary flex items-center justify-center text-[#ea580c]">
            <Shield className="h-4 w-4" />
          </div>
          <div>
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
              {"// ON_CHAIN_DEFENSE"}
            </span>
            <p className="text-xl sm:text-2xl font-bold tracking-tight text-foreground mt-0.5">
              DEMOVAULT_CIRCUIT_BREAKER
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 border border-border bg-secondary text-[11px] font-bold text-emerald-400">
          <span>[SYSTEM_ARMED]</span>
        </div>
      </div>

      {/* Defense Actions List */}
      <div className="space-y-2.5">
        {DEFENSE_MILESTONES.map((item) => {
          const isTriggered = item.status === "triggered";
          const isArmed = item.status === "armed";

          return (
            <div
              key={item.id}
              className={`p-3.5 border transition-all ${
                isTriggered
                  ? "border-[#ea580c] bg-[#ea580c]/5"
                  : isArmed
                  ? "border-border bg-background hover:border-foreground"
                  : "border-border bg-background/50"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div
                    className={`mt-0.5 h-6 w-6 border flex items-center justify-center text-xs ${
                      isTriggered
                        ? "border-[#ea580c] bg-[#ea580c] text-background font-bold"
                        : "border-border bg-secondary text-foreground"
                    }`}
                  >
                    {isTriggered ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-xs font-bold text-foreground uppercase tracking-wider">
                        {item.title}
                      </p>
                      <span
                        className={`text-[9px] px-1 border uppercase font-bold ${
                          isTriggered
                            ? "border-[#ea580c] text-[#ea580c]"
                            : isArmed
                            ? "border-amber-500 text-amber-400"
                            : "border-border text-muted-foreground"
                        }`}
                      >
                        [{item.status}]
                      </span>
                    </div>
                    <p className="text-[10px] text-muted-foreground uppercase mt-0.5">
                      {item.subtitle}
                    </p>
                  </div>
                </div>

                <span className="text-[10px] text-muted-foreground uppercase whitespace-nowrap">
                  {item.threshold}
                </span>
              </div>

              {/* Brutalist Progress Meter */}
              <div className="mt-3 flex items-center gap-2">
                <div className="flex-1 h-2 bg-secondary border border-border overflow-hidden">
                  <div
                    className={`h-full ${
                      isTriggered ? "bg-[#ea580c]" : isArmed ? "bg-foreground" : "bg-muted-foreground"
                    }`}
                    style={{ width: `${item.progress}%` }}
                  />
                </div>
                <span className="text-[10px] font-bold text-foreground">{item.progress}%</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="pt-2">
        <Link
          href="/vault"
          className="flex items-center justify-between p-2.5 border border-dashed border-border bg-muted/10 text-xs font-mono uppercase tracking-wider text-muted-foreground hover:text-foreground hover:border-foreground transition-all"
        >
          <span>INTERACT_WITH_DEMOVAULT &rarr;</span>
          <span className="text-[#ea580c] font-bold">[CONTRACT_CONTROLS]</span>
        </Link>
      </div>
    </div>
  );
}
