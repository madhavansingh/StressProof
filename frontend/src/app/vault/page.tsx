"use client";

import { useState } from "react";

export default function VaultPage() {
  const [collateral, setCollateral] = useState<number>(10000);
  const [borrowAmount, setBorrowAmount] = useState<number>(7000);
  const [borrowStatus, setBorrowStatus] = useState<string | null>(null);

  // Default max LTV: 80% (8000 bps); reduced: 50% (5000 bps)
  const maxLtvBps = 5000;
  const borrowPaused = false;

  function handleTryBorrow() {
    if (borrowPaused) {
      setBorrowStatus("Revert: BorrowPaused()");
      return;
    }
    const requestedLtvBps = Math.ceil((borrowAmount * 10000) / collateral);
    if (requestedLtvBps > maxLtvBps) {
      setBorrowStatus(`Reverted: LtvTooHigh(requested: ${requestedLtvBps} bps, max: ${maxLtvBps} bps)`);
    } else {
      setBorrowStatus(`Success: Borrowed $${borrowAmount.toLocaleString()} at ${(requestedLtvBps / 100).toFixed(2)}% LTV`);
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">DemoVault & Borrow Execution</h1>
        <p className="text-zinc-500">
          Inspect defensive vault controls triggered by finalized risk claims.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-zinc-950">
          <span className="text-xs uppercase font-semibold text-zinc-500">Current Max LTV</span>
          <p className="mt-2 text-3xl font-bold text-amber-600">{(maxLtvBps / 100).toFixed(2)}%</p>
          <p className="mt-1 text-xs text-zinc-400">Reduced from 80.00% by Claim #1</p>
        </div>
        <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-zinc-950">
          <span className="text-xs uppercase font-semibold text-zinc-500">Borrow Switch</span>
          <p className="mt-2 text-3xl font-bold text-emerald-600">Active</p>
          <p className="mt-1 text-xs text-zinc-400">Threshold: $4,000 bad debt</p>
        </div>
      </div>

      <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-zinc-950 space-y-4">
        <h2 className="text-lg font-bold">Interactive Borrowing Simulation</h2>
        <p className="text-xs text-zinc-500">
          Attempt to borrow against MockLendingMarket to test on-chain risk boundaries.
        </p>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-semibold uppercase text-zinc-500">Collateral (USD)</label>
            <input
              type="number"
              value={collateral}
              onChange={(e) => setCollateral(Number(e.target.value))}
              className="mt-1 w-full rounded-lg border p-2 text-sm dark:bg-zinc-900"
            />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase text-zinc-500">Borrow Amount (USD)</label>
            <input
              type="number"
              value={borrowAmount}
              onChange={(e) => setBorrowAmount(Number(e.target.value))}
              className="mt-1 w-full rounded-lg border p-2 text-sm dark:bg-zinc-900"
            />
          </div>
        </div>

        <button
          onClick={handleTryBorrow}
          className="rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-500"
        >
          Try Borrow (Mock Execution)
        </button>

        {borrowStatus && (
          <div
            className={`rounded-xl border p-4 text-sm font-mono ${
              borrowStatus.startsWith("Success")
                ? "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300"
                : "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950/30 dark:text-red-300"
            }`}
          >
            {borrowStatus}
          </div>
        )}
      </div>
    </div>
  );
}
