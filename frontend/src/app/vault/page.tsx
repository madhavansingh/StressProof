"use client";

import { useState } from "react";
import { formatUsd8, formatBps } from "@/lib/format";
import { parseUnits } from "viem";
import { Shield, Lock, AlertTriangle, CheckCircle2, Zap, PauseCircle, PlayCircle } from "lucide-react";

export default function VaultPage() {
  const [collateral, setCollateral] = useState<number>(10000);
  const [borrowAmount, setBorrowAmount] = useState<number>(7000);
  const [borrowStatus, setBorrowStatus] = useState<string | null>(null);

  // Default max LTV: 80% (8000 bps); reduced: 50% (5000 bps)
  const [maxLtvBps, setMaxLtvBps] = useState<number>(5000);
  const [borrowPaused, setBorrowPaused] = useState<boolean>(false);

  function handleTryBorrow() {
    if (borrowPaused) {
      setBorrowStatus("REVERT: BorrowPaused() — Emergency circuit breaker tripped by unhedged bad debt.");
      return;
    }
    const requestedLtvBps = Math.ceil((borrowAmount * 10000) / collateral);
    if (requestedLtvBps > maxLtvBps) {
      setBorrowStatus(
        `REVERT: LtvTooHigh(requested: ${requestedLtvBps} bps [${(requestedLtvBps / 100).toFixed(
          2
        )}%], max: ${maxLtvBps} bps [${(maxLtvBps / 100).toFixed(2)}%])`
      );
    } else {
      setBorrowStatus(
        `SUCCESS: Borrowed ${formatUsd8(parseUnits(borrowAmount.toString(), 8))} against ${formatUsd8(
          parseUnits(collateral.toString(), 8)
        )} at ${(requestedLtvBps / 100).toFixed(2)}% LTV.`
      );
    }
  }

  return (
    <div className="max-w-5xl space-y-6 font-mono">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground uppercase break-words">
              DEMOVAULT_RISK_CONTROLS
            </h1>
            <span className="px-2 py-0.5 border border-border bg-secondary text-foreground text-[10px] font-bold uppercase tracking-wider shrink-0">
              DEMOVAULT.SOL
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed uppercase">
            Automated on-chain circuit breakers dynamically tightened when bonded bad debt claims finalize.
          </p>
        </div>

        <button
          onClick={() => setBorrowPaused(!borrowPaused)}
          className={`w-full sm:w-auto px-4 py-2 text-xs font-bold uppercase tracking-wider border-2 transition-all shrink-0 ${
            borrowPaused
              ? "border-emerald-500 bg-emerald-950/60 text-emerald-300"
              : "border-rose-500 bg-rose-950/60 text-rose-300"
          }`}
        >
          {borrowPaused ? "RESUME_BORROWING" : "EMERGENCY_PAUSE_CIRCUIT"}
        </button>
      </div>

      {/* 2 Top Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card border-2 border-border p-5 flex flex-col justify-between space-y-3">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // CURRENT_MAX_LTV
            </span>
            <Shield className="h-4 w-4 text-[#ea580c]" />
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              <p className="text-3xl font-bold text-[#ea580c]">{(maxLtvBps / 100).toFixed(2)}%</p>
              <span className="text-xs text-muted-foreground line-through">80.00%</span>
            </div>
            <span className="text-[10px] text-muted-foreground uppercase">
              DYNAMICALLY REDUCED BY CLAIM #1
            </span>
          </div>
        </div>

        <div className="bg-card border-2 border-border p-5 flex flex-col justify-between space-y-3">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-widest">
              // CIRCUIT_BREAKER_STATUS
            </span>
            <Lock className="h-4 w-4 text-[#ea580c]" />
          </div>
          <div>
            <p className="text-3xl font-bold text-foreground">
              {borrowPaused ? "HALTED" : "OPERATIONAL"}
            </p>
            <span className="text-[10px] text-muted-foreground uppercase">
              PAUSE_THRESHOLD: $4,000.00 BAD DEBT
            </span>
          </div>
        </div>
      </div>

      {/* Borrow Simulator Interactive Bench */}
      <div className="bg-card border-2 border-border p-5 space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-widest text-foreground border-b-2 border-border pb-2">
          // TEST_BORROW_TRANSACTION
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
              COLLATERAL_DEPOSIT ($)
            </label>
            <input
              type="number"
              value={collateral}
              onChange={(e) => setCollateral(Number(e.target.value))}
              className="w-full bg-background border-2 border-border p-2.5 text-xs text-foreground font-mono focus:border-foreground outline-none"
            />
          </div>

          <div>
            <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
              REQUESTED_BORROW ($)
            </label>
            <input
              type="number"
              value={borrowAmount}
              onChange={(e) => setBorrowAmount(Number(e.target.value))}
              className="w-full bg-background border-2 border-border p-2.5 text-xs text-foreground font-mono focus:border-foreground outline-none"
            />
          </div>
        </div>

        <button
          onClick={handleTryBorrow}
          className="w-full py-3 bg-[#ea580c] text-white text-xs font-bold uppercase tracking-wider hover:bg-foreground hover:text-background transition-all border-2 border-[#ea580c] shadow-[3px_3px_0px_0px_hsl(var(--border))]"
        >
          SUBMIT_BORROW_REQUEST
        </button>

        {borrowStatus && (
          <div className="p-3 border-2 border-border bg-background text-xs text-foreground">
            {borrowStatus}
          </div>
        )}
      </div>
    </div>
  );
}
